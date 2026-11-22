import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import select, text
from app import eve_import, main, risk
from app.models import Event, EventEvidence, RiskEvaluation
from app.suricata import adapt_line, EveLineError


def eve(**overrides):
    return {"timestamp": "2026-11-21T12:00:00.123456-0600", "event_type": "alert",
            "src_ip": "2001:0db8:0:0:0:0:0:1", "dest_ip": "198.51.100.2",
            "src_port": 4444, "dest_port": 443, "proto": "TCP",
            "alert": {"signature": "Synthetic test, not IDS capture", "signature_id": 990001,
                      "category": "A Network Trojan was detected", "severity": 1}, **overrides}


def line(record=None):
    return json.dumps(eve() if record is None else record).encode()


def adapt(raw):
    return adapt_line(raw, sensor_id="lab01", filename="eve.json", import_id="test", line_number=1)


def upload(client, headers, data, sensor="lab01", filename="eve.json"):
    return client.post("/api/events/import/eve", params={"filename":filename,"sensor_id":sensor},
        headers={**headers,"Content-Type":"application/x-ndjson"}, content=data)


def test_adapter_normalization_and_evidence():
    raw = line()
    record = adapt(raw)
    assert record.event.event_timestamp.isoformat() == "2026-11-21T18:00:00.123456+00:00"
    assert record.event.source_ip == "2001:db8::1"
    assert record.event.event_type == "malware" and record.event.severity == 100
    assert record.event.asset_criticality == 50
    assert "asset_criticality" not in record.event.model_fields_set
    metadata = json.loads(record.attributes["adapter_metadata"])
    assert metadata["source_port"] == 4444 and metadata["destination_port"] == 443
    assert metadata["protocol"] == "TCP" and metadata["signature_id"] == 990001
    assert metadata["asset_criticality"]["observed"] is False
    assert record.raw_event.encode() == raw
    assert record.evidence["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert adapt(json.dumps(json.loads(raw), sort_keys=True, indent=None).encode()).fingerprint == record.fingerprint
    assert adapt(b"\xef\xbb\xbf" + raw).fingerprint == record.fingerprint


@pytest.mark.parametrize("changes", [
    {"timestamp":"2026-11-21T18:00:00"}, {"timestamp":12345}, {"src_ip":"not-an-ip"},
    {"dest_port":True}, {"src_port":"80"}, {"src_port":65536}, {"proto":4},
    {"alert":{"severity":"1"}}, {"alert":{"severity":False}}, {"alert":{"severity":-1}},
    {"alert":{"signature_id":-1}}, {"alert":{"signature_id":1.1}}, {"alert":[]},
    {"extra":"\x00"}, {"extra":"\ud800"},
])
def test_adapter_rejects_invalid_types(changes):
    with pytest.raises(EveLineError):
        adapt(line(eve(**changes)))


def test_unknown_and_missing_fields_are_explicit():
    record = adapt(line(eve(alert={}, src_ip=None, dest_ip=None, src_port=None)))
    assert record.event.event_type == "desconocido" and record.event.severity == 50
    metadata = json.loads(record.attributes["adapter_metadata"])
    assert metadata["classification"]["matched"] is False and metadata["severity_defaulted"] is True
    record = adapt(line(eve(alert={"category":"Potentially Bad Traffic","signature":"MALWARE exfiltration scan"})))
    assert record.event.event_type == "desconocido"  # no signature heuristics
    assert adapt(line({"event_type":"dns"})) is None
    for raw in (b'null', b'{"event_type":"alert","event_type":"dns"}', b'{"event_type":"alert","x":NaN}'):
        with pytest.raises(EveLineError):
            adapt(raw)


@pytest.mark.parametrize("role", ["administrador","analista","observador"])
def test_permissions_and_six_synthetic_categories(api, headers, role):
    client, session, _ = api
    data = (Path(__file__).resolve().parents[2]/"examples/suricata_sintetico.eve.jsonl").read_bytes()
    assert upload(client, {}, data).status_code == 401
    h = headers(role)
    response = upload(client, h, data)
    assert response.status_code == (403 if role == "observador" else 200)
    if role == "observador":
        assert upload(client, headers("analista"), data).status_code == 200
    else:
        assert response.json()["imported"] == 6 and response.json()["discarded"] == 0
    assert {i["event_type"] for i in client.get("/api/incidents", headers=h).json()} == {
        "acceso_no_autorizado","malware","dos","escaneo","uso_indebido","exfiltracion"}
    with session() as db:
        event_id = db.scalar(select(Event.id))
    assert client.get(f"/api/events/{event_id}").status_code == 401
    assert client.get(f"/api/events/{event_id}", headers=h).json()["adapter_metadata"]["adapter_version"] == "suricata-eve-v1"
    assert len(client.get(f"/api/events/{event_id}/evidence",headers=h).json()) == 1


def test_partial_errors_and_stable_duplicates(api, headers):
    client, session, _ = api
    h = headers("analista")
    raw = line()
    payload = raw + b'\nnot json\n\xff\n' + line({"event_type":"flow"}) + b'\n' + line(eve(alert={}))
    report = upload(client, h, payload).json()
    assert (report["imported"],report["duplicates"],report["discarded"],report["processed"],report["unknown"]) == (2,0,3,5,1)
    assert [e["line"] for e in report["errors"]] == [2,3]
    assert report["complete"] is True
    report = upload(client, h, json.dumps(eve(),sort_keys=True).encode(), filename="renamed.json").json()
    assert report["duplicates"] == 1 and report["imported"] == 0
    with session() as db:
        event = db.scalar(select(Event).where(Event.event_type=="malware"))
        assert event.raw_event == raw.decode() and event.asset_criticality_observed is False
        evidences = db.scalars(select(EventEvidence).where(EventEvidence.event_id==event.id)).all()
        assert {e.filename for e in evidences} == {"eve.json","renamed.json"}
        iid = event.incident_id
    assert len(client.get(f"/api/incidents/{iid}/evaluations",headers=h).json()) == 1
    assert upload(client, h, raw, sensor="other-sensor").json()["imported"] == 1
    assert client.get("/api/events/missing",headers=h).status_code == 404
    assert client.get("/api/events/missing/evidence",headers=h).status_code == 404
    assert client.post("/api/events/import/eve",content=raw,headers={**h,"Content-Type":"multipart/form-data"}).status_code == 415


def test_stream_batching_limits_and_recovery(api, headers, monkeypatch):
    client, session, _ = api
    h = headers("analista")
    monkeypatch.setattr(eve_import,"BATCH_SIZE",2)
    monkeypatch.setattr(eve_import,"MAX_LINE_BYTES",600)
    monkeypatch.setattr(eve_import,"MAX_ERRORS",2)
    valid = [json.dumps(eve(alert={"signature_id":i,"signature":"Sintético ñ"}), ensure_ascii=False).encode() for i in range(5)]
    data = b'\n'.join([*valid[:2], b'x'*700, b'bad', b'bad', *valid[2:]])
    async def chunks():
        for i in range(len(data)):
            yield data[i:i+1]  # Deliberately split every multibyte UTF-8 character.
    report = asyncio.run(eve_import.import_stream(chunks(),author_id=client.get("/api/auth/me",headers=h).json()["id"],
        sensor_id="stream",filename="stream.eve",session_factory=session))
    assert (report["imported"],report["discarded"],report["batches"],report["errors_omitted"]) == (5,3,3,1)
    assert report["errors"][0]["code"] == "line_too_large"
    monkeypatch.setattr(eve_import,"MAX_RECORDS",2)
    response = upload(client,h,b'\n'.join(valid),sensor="limited")
    assert response.status_code == 413
    assert response.json()["imported"] == 2 and response.json()["complete"] is False
    monkeypatch.setattr(eve_import,"MAX_FILE_BYTES",len(valid[0])+1)
    response = upload(client,h,valid[0]+b'\n'+valid[1],sensor="bytes")
    assert response.status_code == 413
    assert response.json()["imported"] == 1 and response.json()["errors"][-1]["code"] == "file_too_large"


@pytest.mark.parametrize("api", ["0003"], indirect=True)
def test_migration_0004_preserves_all_data_and_legacy_fingerprint(api, headers):
    client, session, config = api
    item = main.EventIn(source="legacy",event_timestamp="2026-11-21T18:00:00Z",event_type="dos",severity=80)
    raw = item.model_dump(mode="json")
    fp = hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
    params = {**risk.parameters(),"algorithm_version":"weighted-v1"}
    with session.begin() as db:
        uid=db.execute(text("SELECT id FROM users WHERE username='analista'")).scalar()
        db.execute(text("INSERT INTO incidents (id,correlation_key,event_type,status,score,priority,explanation,created_at,risk_parameters) VALUES ('old','old','dos','Cerrado',80,'Alta',:ex,CURRENT_TIMESTAMP,:params)"),{"ex":'{"old":true}',"params":json.dumps(params)})
        db.execute(text("INSERT INTO events (id,fingerprint,source,event_timestamp,received_at,event_type,severity,asset_criticality,message,raw_event,incident_id) VALUES ('old',:fp,'legacy',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'dos',80,50,'',:raw,'old')"),{"fp":fp,"raw":json.dumps(raw)})
        db.execute(text("INSERT INTO risk_evaluations (id,incident_id,algorithm_version,explanation,score,priority,event_count,created_at) VALUES ('r','old','weighted-v1',:ex,80,'Alta',1,CURRENT_TIMESTAMP)"),{"ex":'{"old":true}'})
        db.execute(text("INSERT INTO incident_history (id,incident_id,author_id,status,justification,created_at) VALUES ('h','old',:uid,'Cerrado','legacy',CURRENT_TIMESTAMP)"),{"uid":uid})
        db.execute(text("INSERT INTO response_actions (id,incident_id,author_id,description,created_at) VALUES ('a','old',:uid,'legacy',CURRENT_TIMESTAMP)"),{"uid":uid})
        tables=("users","incidents","events","risk_evaluations","incident_history","response_actions")
        before={t:db.execute(text(f"SELECT * FROM {t}")).mappings().all() for t in tables}
    command.upgrade(config,"head")
    command.upgrade(config,"head")
    with session() as db:
        for table, rows in before.items():
            after=db.execute(text(f"SELECT * FROM {table}")).mappings().all()
            assert [{k:row[k] for k in rows[0].keys()} for row in after] == rows
        assert db.get(Event,"old").asset_criticality_observed is None
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0005"
    h=headers("analista")
    assert client.post("/api/events/import",json={"events":[raw]},headers=h).json()["duplicates"] == 1
    assert client.get("/api/events/old/evidence",headers=h).json() == []
    assert upload(client,h,line()).json()["imported"] == 1


def test_asset_provenance_and_frozen_v1(api, headers):
    client, session, _=api
    h=headers("analista")
    upload(client,h,line())
    iid=client.get("/api/incidents",headers=h).json()[0]["id"]
    result=client.get(f"/api/incidents/{iid}",headers=h).json()["explanation"]
    assert result["algorithm_version"] == "weighted-v2"
    assert result["factors"]["asset_criticality"]["observed"] is False
    assert result["factors"]["asset_criticality"]["basis"] == "policy_default_50"
    # Existing v1 incidents keep their exact algorithm and provenance semantics.
    with session.begin() as db:
        inc=db.get(main.Incident,iid)
        params=json.loads(inc.risk_parameters)
        params["algorithm_version"]="weighted-v1"
        inc.risk_parameters=json.dumps(params)
    upload(client,h,line(eve(alert={**eve()["alert"],"signature":"second"})))
    rows=client.get(f"/api/incidents/{iid}/evaluations",headers=h).json()
    assert rows[0]["explanation"] == result
    assert rows[-1]["algorithm_version"] == "weighted-v1"
    assert "basis" not in rows[-1]["explanation"]["factors"]["asset_criticality"]
