import csv
import io
import json
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from pydantic import ValidationError
from sqlalchemy import text
from app import evaluation_metrics as m
from app.evaluation_data import synthetic, ExternalDataset
from app.experiments import rank_cases
from app.risk import parameters


def test_accuracy_matrix_f1_and_binary():
    predicted = dict(zip("abcd", ["Baja","Alta","Alta","Media"]))
    refs = {k:{"priority":v,"malicious":i>=2} for i,(k,v) in enumerate(zip("abcd",m.CLASSES))}
    result=m.classification(predicted,refs)
    assert result["matrix"] == [[1,0,0,0],[0,0,1,0],[0,0,1,0],[0,1,0,0]]
    assert result["accuracy"]["value"] == .5
    assert result["per_class"]["Alta"]["precision"]["value"] == .5
    assert result["per_class"]["Alta"]["recall"]["value"] == 1
    assert result["per_class"]["Alta"]["f1"]["value"] == pytest.approx(2/3)
    assert result["macro"]["f1"]["value"] == pytest.approx(5/12)
    assert result["macro"]["precision"]["value"] is None
    assert m.false_positive_rate(predicted,refs)["rate"]["value"] == .5
    perfect=m.classification(dict(zip("abcd",m.CLASSES)),refs)
    assert perfect["accuracy"]["value"] == perfect["macro"]["f1"]["value"] == 1


def test_metrics_missing_zero_denominators_and_budget():
    assert m.classification({}, {})["accuracy"]["status"] == "No calculable"
    assert m.classification({"a":"Baja"},{})["matrix"] is None
    assert m.false_positive_rate({"a":"Baja"},{"a":{"priority":"Baja"}})["rate"]["value"] is None
    assert m.false_positive_rate({"a":"Alta"},{"a":{"malicious":True}})["rate"]["value"] is None
    refs={"a":{"priority":"Crítica"},"b":{"priority":"Baja"}}
    assert m.attention(["a","b"],refs,0,{"a":2,"b":3})["critical_coverage"]["value"] == 0
    result=m.attention(["b","a"],refs,1,{"a":2,"b":3})
    assert result["critical_coverage"]["value"] == 0 and result["selected_events"]["value"] == 3
    assert m.attention(["b"],refs,1,{"b":3})["critical_coverage"]["value"] is None


def test_times_require_complete_observed_evidence():
    ref={"occurred_at":"2026-01-01T00:00:00+00:00","detected_at":"2026-01-01T00:02:00+00:00",
         "response_completed_at":"2026-01-01T00:10:00+00:00","timing_evidence":"authorized source timing log"}
    result=m.timing(["a"],{"a":ref},"controlled")
    assert result["mttd"]["value"] == 120 and result["mttr"]["value"] == 480
    assert m.timing(["a"],{"a":ref},"synthetic")["mttd"]["value"] is None
    assert m.timing(["a","b"],{"a":ref},"real")["mttr"]["value"] is None
    bad={**ref,"detected_at":"2025-01-01T00:00:00+00:00"}
    assert m.timing(["a"],{"a":bad},"real")["mttr"]["value"] is None


def test_generator_reproducibility_independent_labels_and_ties():
    a,b=synthetic(),synthetic()
    assert a.model_dump() == b.model_dump()
    assert a.model_dump() != synthetic(5).model_dump()
    assert len({c.event_type for c in a.cases}) == 6
    orders,predictions=rank_cases(a.cases,parameters())
    assert any(predictions[str(r.case_id)]["priority"] != r.priority for r in a.references)
    tied=deepcopy(a.cases[:2])
    for c in tied:
        c.event_type="dos"
        c.events=c.events[:1]
        c.events[0].received_at=datetime(2026,1,1,tzinfo=timezone.utc)
        c.events[0].severity=50
        c.events[0].asset_criticality=50
    order,_=rank_cases(list(reversed(tied)),parameters())
    assert order["chronological"] == order["smartir"] == sorted(str(c.id) for c in tied)


@pytest.mark.parametrize("change", ["reference_in_features","unauthorized","duplicate_case","invalid_time","duplicate_reference"])
def test_dataset_validation(change):
    data=synthetic(count=6).model_dump(mode="json")
    if change=="reference_in_features": data["cases"][0]["priority"]="Crítica"
    elif change=="unauthorized": data["authorized"]=False
    elif change=="duplicate_case": data["cases"][1]=data["cases"][0]
    elif change=="invalid_time": data["references"][0]["detected_at"]="2026-01-01T00:00:00"
    else: data["references"].append(data["references"][0])
    with pytest.raises(ValidationError): ExternalDataset.model_validate(data)


def test_replay_results_exports_and_no_operational_writes(api,headers):
    client,session,_=api
    h=headers("administrador")
    first=client.post("/api/evaluation/datasets/synthetic",json={"seed":202605,"count":60},headers=h)
    assert first.status_code==201
    did=first.json()["id"]
    second=client.post("/api/evaluation/datasets/synthetic",json={"seed":202605,"count":60},headers=h).json()
    assert first.json()["feature_hash"] == second["feature_hash"]
    def run(dataset):return client.post("/api/evaluation/experiments",json={"dataset_id":dataset,"budget":10},headers=h).json()
    a,b=run(did),run(second["id"])
    assert a["rankings"]==b["rankings"] and a["results"]==b["results"]
    assert a["results"]["timing"]["mttd"]["status"]=="No calculable"
    assert a["configuration"]["effective_budget"]==10
    assert set(a["rankings"]["orders"]["chronological"])==set(a["rankings"]["orders"]["smartir"])
    exported=client.get(f'/api/evaluation/experiments/{a["id"]}/export',headers=h)
    assert exported.status_code==200 and len(exported.json()["references"])==60
    csv_response=client.get(f'/api/evaluation/experiments/{a["id"]}/export?format=csv',headers=h)
    rows=list(csv.DictReader(io.StringIO(csv_response.text)))
    assert json.loads(rows[0]["value"])["configuration"]["risk_parameters"]["algorithm_version"] == "weighted-v2"
    assert len([r for r in rows if r["record"]=="case"])==120
    case_row=next(r for r in rows if r["record"]=="case")
    assert "malicious" in json.loads(case_row["reference_json"])
    assert len(json.loads(case_row["features_json"])["events"])>=1
    assert any(r["record"]=="metric" and r["status"]=="No calculable" for r in rows)
    assert client.get(f'/api/evaluation/experiments/{a["id"]}/export?format=zip',headers=h).status_code==422
    with session() as db:
        for table in ("incidents","events","risk_evaluations"):
            assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar()==0


def test_references_do_not_change_predictions_or_orders(api,headers):
    client,_,_=api
    h=headers("administrador")
    original=synthetic(count=6).model_dump(mode="json")
    changed=deepcopy(original)
    for r in changed["references"]:r["priority"]="Baja";r["malicious"]=False;r["rationale"]="Different independent reference"
    results=[]
    for payload in (original,changed):
        did=client.post("/api/evaluation/datasets/import",json=payload,headers=h).json()["id"]
        results.append(client.post("/api/evaluation/experiments",json={"dataset_id":did,"budget":2},headers=h).json())
    assert results[0]["rankings"]==results[1]["rankings"]
    assert results[0]["results"]["classification"]!=results[1]["results"]["classification"]


@pytest.mark.parametrize("role",["analista","observador"])
def test_blinding_and_permissions(api,headers,role):
    client,_,_=api
    admin=headers("administrador")
    did=client.post("/api/evaluation/datasets/synthetic",json={"count":6},headers=admin).json()["id"]
    experiment=client.post("/api/evaluation/experiments",json={"dataset_id":did,"budget":2},headers=admin).json()
    h=headers(role)
    for path,payload in (("datasets/synthetic",{}),("datasets/import",synthetic(count=6).model_dump(mode="json")),("experiments",{"dataset_id":did})):
        assert client.post('/api/evaluation/'+path,json=payload,headers=h).status_code==403
    for path in (f'datasets/{did}/export',f'experiments/{experiment["id"]}/export'):
        assert client.get('/api/evaluation/'+path,headers=h).status_code==403
    cases=client.get(f'/api/evaluation/datasets/{did}/cases',headers=h).json()
    assert "rationale" not in json.dumps(cases) and "malicious" not in json.dumps(cases)
    visible=client.get(f'/api/evaluation/experiments/{experiment["id"]}',headers=h).json()
    assert "results" not in visible and "dataset_configuration" not in visible["configuration"]
    assert "seed" not in json.dumps(client.get('/api/evaluation/datasets',headers=h).json())
    assert client.get('/api/evaluation/experiments').status_code==401


def test_errors_missing_labels_and_limits(api,headers):
    client,_,_=api
    h=headers("administrador")
    assert client.post('/api/evaluation/datasets/import',json={"authorized":False},headers=h).status_code==422
    assert client.post('/api/evaluation/datasets/import',content=b'x'*(2*1024*1024+1),headers=h).status_code==413
    assert client.post('/api/evaluation/experiments',json={"dataset_id":str(uuid4())},headers=h).status_code==404
    data=synthetic(count=6).model_dump(mode="json");data["references"]=[]
    did=client.post('/api/evaluation/datasets/import',json=data,headers=h).json()["id"]
    result=client.post('/api/evaluation/experiments',json={"dataset_id":did,"budget":500},headers=h).json()
    assert result["configuration"]["effective_budget"]==6
    assert result["results"]["classification"]["accuracy"]["status"]=="No calculable"
    assert client.post('/api/evaluation/experiments',json={"dataset_id":did,"budget":-1},headers=h).status_code==422


def test_operational_traceability_and_atomic_rejection(api,headers,batch):
    client,session,_=api
    h=headers("administrador")
    client.post('/api/events/import',json=batch,headers=h)
    with session() as db:
        event=db.execute(text('SELECT * FROM events LIMIT 1')).mappings().one()
        event_id,incident_id=event['id'],event['incident_id']
        from app.models import Event
        model=db.get(Event,event_id)
        payload=synthetic(count=6).model_dump(mode='json')
        case=payload['cases'][0]
        case['incident_id']=incident_id
        case['event_type']=model.event_type
        case['events']=[{'id':str(uuid4()),'operational_event_id':event_id,
            'event_timestamp':model.event_timestamp.replace(tzinfo=timezone.utc).isoformat(),
            'received_at':model.received_at.replace(tzinfo=timezone.utc).isoformat(),
            'severity':model.severity,'asset_criticality':model.asset_criticality}]
    response=client.post('/api/evaluation/datasets/import',json=payload,headers=h)
    assert response.status_code==201
    with session() as db:
        assert db.execute(text('SELECT event_id FROM evaluation_event_links')).scalar()==event_id
    case['events'][0]['severity']=(case['events'][0]['severity']+1)%101
    assert client.post('/api/evaluation/datasets/import',json=payload,headers=h).status_code==422
    assert len(client.get('/api/evaluation/datasets',headers=h).json())==1


@pytest.mark.parametrize("api",["0004"],indirect=True)
def test_additive_0005_migration(api):
    _,session,config=api
    tables=("users","events","incidents","risk_evaluations","event_evidence","incident_history","response_actions")
    with session.begin() as db:
        uid=db.execute(text("SELECT id FROM users LIMIT 1")).scalar()
        db.execute(text("INSERT INTO incidents(id,correlation_key,event_type,status,score,priority,explanation,created_at) VALUES('legacy','old','dos','Cerrado',10,'Baja','{}',CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO events(id,fingerprint,source,event_timestamp,received_at,event_type,severity,asset_criticality,message,raw_event,incident_id) VALUES('e','fp','old',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'dos',10,50,'old','{}','legacy')"))
        db.execute(text("INSERT INTO risk_evaluations(id,incident_id,algorithm_version,explanation,score,priority,event_count,created_at) VALUES('r','legacy','weighted-v1','{}',10,'Baja',1,CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO event_evidence(id,event_id,author_id,import_id,filename,sensor_id,line_number,raw_line,raw_sha256,created_at) VALUES('proof','e',:uid,'old','old','old',1,'{}','fp',CURRENT_TIMESTAMP)"),{"uid":uid})
        before={t:db.execute(text(f"SELECT * FROM {t}")).mappings().all() for t in tables}
    command.upgrade(config,'head');command.upgrade(config,'head')
    with session() as db:
        for table in tables: assert db.execute(text(f"SELECT * FROM {table}")).mappings().all()==before[table]
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0006'
