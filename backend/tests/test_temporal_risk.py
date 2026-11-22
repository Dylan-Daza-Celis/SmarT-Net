import json
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from alembic import command
from sqlalchemy import text
from app import main, risk
from app.correlation import correlate


def event(timestamp="2026-11-21T18:00:00Z", **overrides):
    return {"source": "test", "event_timestamp": timestamp, "event_type": "dos",
            "source_ip": "192.0.2.1", "destination_ip": "192.0.2.2",
            "severity": 80, "asset_criticality": 60, **overrides}


def test_windows_late_order_boundaries_duplicates(api, headers):
    client, _, _ = api
    h = headers("analista")
    late = event("2026-11-21T18:14:59.999999Z")
    first = client.post("/api/events/import", json={"events": [late]}, headers=h)
    assert first.json()["incidents_updated"] == 1
    iid = client.get("/api/incidents", headers=h).json()[0]["id"]
    batch = [event(), event("2026-11-21T18:15:00Z"), event("2026-11-22T18:00:00Z")]
    assert client.post("/api/events/import", json={"events": batch}, headers=h).json()["imported"] == 3
    items = client.get("/api/incidents", headers=h).json()
    assert len(items) == 3
    assert next(i for i in items if i["id"] == iid)["event_count"] == 2
    before = client.get(f"/api/incidents/{iid}/evaluations", headers=h).json()
    assert [r["event_count"] for r in before] == [1, 2]
    response = client.post("/api/events/import", json={"events": [late, *batch]}, headers=h)
    assert response.json() == {"imported": 0, "duplicates": 4, "incidents_updated": 0}
    assert client.get(f"/api/incidents/{iid}/evaluations", headers=h).json() == before
    assert client.get(f"/api/incidents/{iid}/evaluations").status_code == 401


def test_addresses_missing_and_utc(api, headers):
    client, _, _ = api
    h = headers("analista")
    events = [event(), event(source_ip="192.0.2.3"), event(destination_ip="192.0.2.4"),
              event(source_ip=None), event(source_ip=None, message="same missing source"),
              event(source_ip=None, destination_ip=None), event(event_type="malware"),
              event("2026-11-21T12:01:00-06:00", message="same UTC window")]
    assert client.post("/api/events/import", json={"events": events}, headers=h).status_code == 200
    items = client.get("/api/incidents", headers=h).json()
    assert len(items) == 6
    assert sorted(i["event_count"] for i in items) == [1, 1, 1, 1, 2, 2]
    assert client.post("/api/events/import", json={"events": [event(source_ip="invalid")]}, headers=h).status_code == 422
    assert correlate(main.EventIn(**event(source_ip="2001:db8::1")))[0] == correlate(main.EventIn(**event(source_ip="2001:0db8:0:0:0:0:0:1")))[0]


def test_configurable_window():
    item = main.EventIn(**event("2026-11-21T18:06:00Z"))
    assert correlate(item, 300)[1] == datetime(2026, 11, 21, 18, 5, tzinfo=timezone.utc)
    assert correlate(item, 900)[1] == datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)


def test_scoring_extremes_and_contributions():
    params = risk.parameters()
    low = SimpleNamespace(severity=0, asset_criticality=0, event_type="unknown")
    result = risk.evaluate([low], params)
    assert result["score"] == 14  # 0 + 0 + 3 + 6 + 5
    assert result["priority"] == "Baja"
    high = SimpleNamespace(severity=100, asset_criticality=100, event_type="exfiltracion")
    result = risk.evaluate([high] * 5, params)
    assert result["score"] == 95  # unknown context contributes 5, not 10
    assert result["priority"] == "Crítica"
    assert sum(f["contribution"] for f in result["factors"].values()) == result["unrounded_score"]
    assert result["context"]["known"] is False
    assert result["factors"]["context"]["observed"] is False
    assert result["parameters"] == params
    rounded = risk.evaluate([SimpleNamespace(severity=10, asset_criticality=0, event_type="unknown")], params)
    assert rounded["unrounded_score"] == 17.5 and rounded["score"] == 18
    params["unknown_context"] = 0
    params["unknown_attack"] = 0
    params["recurrence_per_event"] = 0
    assert risk.evaluate([low], params)["score"] == 0
    params["unknown_context"] = 100
    assert risk.evaluate([high] * 5, {**params, "recurrence_per_event":20})["score"] == 100
    for score, label in [(0,"Baja"),(24,"Baja"),(25,"Media"),(49,"Media"),(50,"Alta"),(74,"Alta"),(75,"Crítica"),(100,"Crítica")]:
        assert risk.priority(score) == label


def test_parameters_frozen_and_evaluations_preserved(api, headers, monkeypatch):
    client, _, _ = api
    h = headers("analista")
    client.post("/api/events/import", json={"events":[event()]}, headers=h)
    iid = client.get("/api/incidents", headers=h).json()[0]["id"]
    previous = client.get(f"/api/incidents/{iid}/evaluations", headers=h).json()[0]
    monkeypatch.setitem(risk.DEFAULT_PARAMETERS, "unknown_context", 0)
    client.post("/api/events/import", json={"events":[event(message="second")]}, headers=h)
    rows = client.get(f"/api/incidents/{iid}/evaluations", headers=h).json()
    assert rows[0] == previous
    assert rows[1]["explanation"]["parameters"]["unknown_context"] == 50


@pytest.mark.parametrize("api", ["0002"], indirect=True)
def test_legacy_preserved_and_excluded(api, headers):
    client, session, config = api
    raw = main.EventIn(**event()).model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    with session.begin() as db:
        db.execute(text("INSERT INTO incidents (id,correlation_key,event_type,destination_ip,status,score,priority,explanation,created_at) VALUES ('legacy','dos|192.0.2.2','dos','192.0.2.2','Cerrado',87,'Alta',:explanation,CURRENT_TIMESTAMP)"), {"explanation":json.dumps({"legacy":True})})
        db.execute(text("INSERT INTO events (id,fingerprint,source,event_timestamp,received_at,event_type,severity,asset_criticality,message,raw_event,incident_id) VALUES ('old',:fp,'test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'dos',80,60,'old',:raw,'legacy')"), {"fp":fingerprint,"raw":json.dumps(raw)})
        uid = db.execute(text("SELECT id FROM users WHERE username='analista'")).scalar()
        db.execute(text("INSERT INTO incident_history (id,incident_id,author_id,status,justification,created_at) VALUES ('h','legacy',:uid,'Cerrado','old',CURRENT_TIMESTAMP)"), {"uid":uid})
        db.execute(text("INSERT INTO response_actions (id,incident_id,author_id,description,created_at) VALUES ('a','legacy',:uid,'old',CURRENT_TIMESTAMP)"), {"uid":uid})
    command.upgrade(config, "head")
    h = headers("analista")
    old = client.get("/api/incidents/legacy", headers=h).json()
    assert old["score"] == 87 and old["status"] == "Cerrado" and old["event_count"] == 1
    assert old["explanation"] == {"legacy":True} and old["correlation_version"] == "legacy"
    assert client.post("/api/events/import", json={"events":[event()]}, headers=h).json() == {"imported":0,"duplicates":1,"incidents_updated":0}
    assert client.post("/api/events/import", json={"events":[event(message="new event")]}, headers=h).json()["imported"] == 1
    assert client.get("/api/incidents/legacy", headers=h).json() == old
    assert len(client.get("/api/incidents/legacy/history", headers=h).json()) == 1
    assert len(client.get("/api/incidents/legacy/actions", headers=h).json()) == 1
    evaluation = client.get("/api/incidents/legacy/evaluations", headers=h).json()[0]
    assert evaluation["algorithm_version"] == "legacy-unknown" and evaluation["score"] == 87
