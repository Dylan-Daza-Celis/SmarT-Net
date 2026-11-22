import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import select, text, event as sql_event
from alembic import command
from app.models import (Incident, Event, User, IncidentHistory, AssignmentHistory, IncidentReviewSignal,
                        RiskEvaluation, RiskReassessment, AnalyticsReport, IncidentTimeEvidence, MLRun, EvaluationDataset)
from app.experiments import digest, canonical
from app import analytics_api
from app.analytical_reports import csv_cell

PERIOD={'start':'2026-01-01T00:00:00Z','end':'2026-01-03T00:00:00Z'}
def stamp(day): return datetime(2026,1,day,tzinfo=timezone.utc)


def seed(session):
    with session.begin() as db:
        uid=db.scalar(select(User.id).where(User.role=='analista'))
        incidents=[]
        for n,(priority,state) in enumerate(zip(['Crítica','Alta','Media','Baja','Crítica','Baja'],['Nuevo','En respuesta','Resuelto','Cerrado','Asignado','Nuevo'])):
            inc=Incident(correlation_key=str(uuid4()),event_type='dos' if n%2==0 else 'malware',
                status=state,score=[90,60,40,10,85,5][n],priority=priority,created_at=stamp(1 if n==0 else 2 if n<5 else 3),
                lifecycle_started_at=stamp(1 if n==0 else 2 if n<5 else 3),assigned_to_id=uid if n in (1,4) else None)
            db.add(inc);db.flush();incidents.append(inc.id)
            for j in range(2 if n in (0,1) else 1):
                ev=Event(fingerprint=str(uuid4()),source='eve' if j==0 else 'host',
                    event_timestamp=stamp(3+j if n==0 else 2+j),received_at=stamp(5),
                    event_type=inc.event_type,severity=20,asset_criticality=50,message='private message',
                    source_ip='192.0.2.25',destination_ip='192.0.2.100',raw_event='private raw evidence',incident_id=inc.id)
                db.add(ev);db.flush()
                if n==0 and j==0:
                    db.add(IncidentReviewSignal(incident_id=inc.id,event_id=ev.id,author_id=uid,reason='fixture signal',created_at=stamp(6)))
            if n==1:
                db.add(AssignmentHistory(incident_id=inc.id,author_id=uid,assigned_user_id=uid,justification='fixture',cycle_number=1,created_at=stamp(2)+timedelta(seconds=10)))
                db.add(IncidentHistory(incident_id=inc.id,author_id=uid,previous_status='En análisis',status='En respuesta',justification='fixture',cycle_number=1,policy_version='lifecycle-v1',created_at=stamp(2)+timedelta(seconds=30)))
                db.add(IncidentHistory(incident_id=inc.id,author_id=uid,previous_status='En respuesta',status='Resuelto',justification='fixture',cycle_number=1,policy_version='lifecycle-v1',created_at=stamp(2)+timedelta(seconds=40)))
                db.add(IncidentTimeEvidence(incident_id=inc.id,author_id=uid,cycle_number=1,source_kind='operational',
                    evidence_reference='unit-test attestation, not real operations',review_note='Unit test only',
                    occurred_at=stamp(2),detected_at=stamp(2)+timedelta(seconds=5),response_completed_at=stamp(2)+timedelta(seconds=50),created_at=stamp(6)))
    return incidents,uid


def dashboard(client,h,**q):
    result=client.get('/api/analytics/dashboard',params={**PERIOD,**q},headers=h)
    assert result.status_code==200,result.text
    return result.json()


def test_aggregates_denominators_and_trends(api,headers):
    c,s,_=api;seed(s);d=dashboard(c,headers('observador'))
    assert d['totals']=={'incidents':5,'assigned':2,'open':3,'resolved':1,'closed':1,'needs_review':1,'critical_open':2,'urgent_unassigned':1,'unassigned':3,'events':7}
    for key in ('priority','status','type'): assert sum(r['count'] for r in d['distributions'][key])==5
    assert sum(r['count'] for r in d['distributions']['source'])==7
    assert sum(r['events'] for r in d['trends'])==7
    assert sum(r['incidents'] for r in d['trends'])==5 and sum(r['critical'] for r in d['trends'])==2
    assert d['incidents']['total']==5 and len(d['incidents']['items'])==5
    assert all(m['value'] is None for m in d['response_metrics'].values())
    assert d['provenance']['data_kind']=='unverified'


def test_combined_filters_response_metrics_and_half_open_dates(api,headers):
    c,s,_=api;ids,uid=seed(s);h=headers('analista')
    q={'priority':'Alta','event_type':'malware','status':'En respuesta','assignee':uid,'source':'eve'}
    d=dashboard(c,h,**q)
    assert d['totals']['incidents']==1 and d['totals']['events']==1 and d['incidents']['items'][0]['id']==ids[1]
    assert [d['response_metrics'][k]['value'] for k in ('time_to_assignment','time_to_response','time_to_resolution','mttd','mttr')]==pytest.approx([10,30,40,5,45],abs=.0001)
    assert dashboard(c,h,assignee='unassigned')['totals']['incidents']==3
    assert dashboard(c,h,start='2025-12-31T18:00:00-06:00',end='2026-01-02T18:00:00-06:00')['totals']==dashboard(c,h)['totals']
    assert ids[5] not in [r['id'] for r in dashboard(c,h)['incidents']['items']]


def test_event_and_reception_axes_count_only_matching_events(api,headers):
    c,s,_=api;ids,_=seed(s);h=headers('administrador')
    d=dashboard(c,h,time_basis='event_timestamp')
    assert d['totals']['incidents']==5 and ids[0] not in [r['id'] for r in d['incidents']['items']]
    assert d['totals']['events']==5
    assert sum(r['incidents'] for r in d['trends'])==5
    later=dashboard(c,h,time_basis='event_timestamp',start='2026-01-02T00:00:00Z',end='2026-01-05T00:00:00Z')
    assert later['totals']['incidents']==6 and later['totals']['events']==8
    assert sum(r['incidents'] for r in later['trends'])==6 # one incident with two days still counted once
    assert dashboard(c,h,time_basis='received_at')['totals']['events']==0
    assert dashboard(c,h,time_basis='received_at',start='2026-01-05T00:00:00Z',end='2026-01-06T00:00:00Z')['totals']['events']==8


def test_pagination_and_no_n_plus_one(api,headers):
    c,s,_=api;seed(s);h=headers('observador')
    first=c.get('/api/analytics/incidents',params={**PERIOD,'limit':2},headers=h).json()
    second=c.get('/api/analytics/incidents',params={**PERIOD,'limit':2,'offset':2},headers=h).json()
    assert first['total']==second['total']==5 and len(first['items'])==2
    assert not {r['id'] for r in first['items']}&{r['id'] for r in second['items']}
    engine=s.kw['bind'];queries=[]
    def record(*args): queries.append(args[2])
    sql_event.listen(engine,'before_cursor_execute',record)
    try:
        dashboard(c,h,limit=1);n=len(queries);queries.clear()
        dashboard(c,h,limit=100);assert len(queries)==n
    finally: sql_event.remove(engine,'before_cursor_execute',record)


@pytest.mark.parametrize('params',[{'start':'2026-01-01'},{'start':'2026-01-03T00:00:00Z','end':'2026-01-01T00:00:00Z'},
    {'start':'2020-01-01T00:00:00Z'},{'limit':101},{'offset':-1},{'priority':'Urgente'},{'assignee':'invalid'},
    {'time_basis':'detected_at'},{'source':''},{'unknown':'value'}])
def test_invalid_parameters(api,headers,params):
    c,_,_=api
    assert c.get('/api/analytics/dashboard',params={**PERIOD,**params},headers=headers('observador')).status_code==422


def test_empty_permissions_and_read_only_observer(api,headers):
    c,_,_=api;o=headers('observador')
    for path in ('dashboard','incidents','options','reports'):
        assert c.get('/api/analytics/'+path).status_code==401
        assert c.get('/api/analytics/'+path,headers=o).status_code==200
    assert c.get('/api/analytics/comparisons').status_code==401
    assert c.get('/api/analytics/comparisons',headers=o).status_code==403
    assert 'observador' not in [u['username'] for u in c.get('/api/analytics/options',headers=o).json()['assignees']]
    d=dashboard(c,o)
    assert d['totals']['incidents']==d['totals']['events']==0
    assert all(m['value'] is None for m in d['response_metrics'].values())
    assert c.post('/api/analytics/reports',json=PERIOD,headers=o).status_code==403
    r=c.post('/api/analytics/reports',json=PERIOD,headers=headers('analista'))
    assert r.status_code==201
    assert c.get('/api/analytics/reports/'+r.json()['id'],headers=o).status_code==200
    csv_data=c.get('/api/analytics/reports/'+r.json()['id'],params={'format':'csv'},headers=o).content.decode('utf-8-sig')
    assert 'No calculable' in csv_data


def test_snapshot_exports_are_immutable_consistent_and_sanitized(api,headers):
    c,s,_=api;seed(s);h=headers('administrador');o=headers('observador')
    d=dashboard(c,h,priority='Alta')
    response=c.post('/api/analytics/reports',json={**PERIOD,'priority':'Alta'},headers=h)
    assert response.status_code==201,response.text
    url='/api/analytics/reports/'+response.json()['id']
    initial=c.get(url,headers=o);saved=initial.json();payload=saved['payload']
    assert digest(payload)==saved['content_sha256']==initial.headers['X-Content-SHA256']
    assert payload['dashboard']['totals']==d['totals'] and len(payload['incidents'])==1
    forbidden=('password_hash','Authorization','private message','private raw evidence','192.0.2.','author_id')
    assert all(v not in initial.text for v in forbidden)
    assert all('assignee' not in row and 'assigned_to_id' not in row for row in payload['incidents'])
    csv_result=c.get(url,params={'format':'csv'},headers=o)
    parsed=list(csv.reader(io.StringIO(csv_result.content.decode('utf-8-sig'))))
    assert sum(r[0]=='incident' for r in parsed)==1 and sum(r[0]=='metric' for r in parsed)==5
    pdf=c.get(url,params={'format':'pdf'},headers=o)
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF') and len(pdf.content)>3000
    assert pdf.content==c.get(url,params={'format':'pdf'},headers=o).content
    with s.begin() as db: db.execute(text("UPDATE incidents SET score=0,priority='Baja'"))
    assert c.get(url,headers=o).content==initial.content
    assert c.get('/api/analytics/reports',headers=o).json()['total']==1
    assert c.get(url,params={'format':'xml'},headers=o).status_code==422
    cors=c.get(url,headers={**o,'Origin':'http://localhost:5173'})
    assert 'Content-Disposition' in cors.headers.get('access-control-expose-headers','')
    assert c.get('/api/analytics/reports/missing',headers=o).status_code==404
    with s.begin() as db: db.get(AnalyticsReport,response.json()['id']).payload='{}'
    assert c.get(url,headers=o).status_code==409


def test_export_limits_sql_injection_and_csv_formulas(api,headers,monkeypatch):
    c,s,_=api;seed(s);h=headers('analista');monkeypatch.setattr(analytics_api,'MAX_REPORT_ROWS',1)
    assert c.post('/api/analytics/reports',json=PERIOD,headers=h).status_code==413
    assert dashboard(c,h,source="' OR 1=1 --")['totals']['incidents']==0
    for text_value in ('=1+1',' +SUM(1,1)','@SUM(A1)','\n-1'):
        assert csv_cell(text_value).startswith("'")
    assert csv_cell('eve')=='eve' and csv_cell(0)==0
    monkeypatch.setattr(analytics_api,'MAX_REPORT_BYTES',1)
    assert c.post('/api/analytics/reports',json={**PERIOD,'source':'no-match'},headers=h).status_code==413


def test_latest_nonoperational_evidence_does_not_become_zero(api,headers):
    c,s,_=api;ids,uid=seed(s)
    with s.begin() as db:
        db.add(IncidentTimeEvidence(incident_id=ids[1],author_id=uid,cycle_number=1,source_kind='laboratory',
            evidence_reference='test-only',review_note='Not operational evidence',occurred_at=stamp(2),
            detected_at=stamp(2),response_completed_at=stamp(2),created_at=stamp(7)))
    result=dashboard(c,headers('observador'),priority='Alta')
    assert result['response_metrics']['mttd']['value'] is None and result['response_metrics']['mttr']['value'] is None
    assert result['response_metrics']['time_to_assignment']['value']==pytest.approx(10,abs=.0001)


def test_registered_comparisons_keep_synthetic_label_and_do_not_expose_labels(api,headers):
    c,s,_=api;h=headers('administrador')
    with s.begin() as db:
        uid=db.scalar(select(User.id));d=EvaluationDataset(author_id=uid,name='fixture',data_kind='synthetic',configuration='{}',feature_hash='fixture')
        db.add(d);db.flush()
        metric={'value':.25,'unit':'ratio','status':'Calculable','reason':None}
        db.add(MLRun(dataset_id=d.id,author_id=uid,status='completed',configuration=canonical({'protocol':'test-only','effective_budget':2}),
            artifacts='{"secret_artifact":"not exported"}',results=canonical({'weighted-v2':{'classification':{'accuracy':metric,'macro':{'f1':metric},'total':8},'predictions':{'private_reference':'hidden'}}})))
    result=c.get('/api/analytics/comparisons',headers=h)
    assert result.json()['items'][0]['data_kind']=='synthetic'
    model=result.json()['items'][0]['models'][0]
    assert model['accuracy']['value']==.25 and model['support']==8
    assert 'private_reference' not in result.text and 'secret_artifact' not in result.text


def prepare_reopening(c,h,batch):
    ev={**batch['events'][0],'severity':10,'asset_criticality':10}
    c.post('/api/events/import',json={'events':[ev]},headers=h)
    iid=c.get('/api/incidents',headers=h).json()[0]['id'];path='/api/incidents/'+iid
    def current(): return c.get(path,headers=h).json()
    uid=c.get('/api/auth/me',headers=h).json()['id']
    c.patch(path+'/assignment',json={'assigned_to_id':uid,'justification':'Fixture','expected_revision':current()['revision']},headers=h)
    for status in ('En análisis','En respuesta','Resuelto','Cerrado'):
        assert c.patch(path+'/status',json={'status':status,'justification':'Fixture','expected_revision':current()['revision']},headers=h).status_code==200
    frozen=current()
    late={**ev,'message':'Late synthetic evidence','severity':100,'asset_criticality':100}
    c.post('/api/events/import',json={'events':[late]},headers=h)
    assert c.post(path+'/reevaluate',json={'expected_revision':current()['revision'],'justification':'Fixture'},headers=h).status_code==409
    c.patch(path+'/status',json={'status':'En análisis','justification':'Review new evidence','expected_revision':current()['revision']},headers=h)
    return iid,ev,current,frozen


def test_explicit_reassessment_frozen_parameters_history_and_permissions(api,headers,batch,monkeypatch):
    c,s,_=api;h=headers('administrador');iid,ev,current,frozen=prepare_reopening(c,h,batch)
    path='/api/incidents/'+iid
    previous=c.get(path+'/evaluations',headers=h).json()
    c.post('/api/events/import',json={'events':[{**ev,'message':'Another event after reopening'}]},headers=h)
    assert current()['score']==frozen['score'] and c.get(path+'/evaluations',headers=h).json()==previous
    body={'expected_revision':current()['revision'],'justification':'Review closed evidence with frozen parameters'}
    assert c.post(path+'/reevaluate',json=body,headers=headers('observador')).status_code==403
    assert c.post(path+'/reevaluate',json=body,headers=headers('analista')).status_code==403
    assert c.post(path+'/reevaluate',json={'justification':'Missing revision'},headers=h).status_code==428
    from app.risk import DEFAULT_PARAMETERS
    monkeypatch.setitem(DEFAULT_PARAMETERS,'unknown_context',99)
    result=c.post(path+'/reevaluate',json=body,headers=h)
    assert result.status_code==201,result.text
    assert result.json()['score']>frozen['score'] and current()['risk_reevaluation_pending'] is False
    evaluations=c.get(path+'/evaluations',headers=h).json()
    assert evaluations[:-1]==previous and evaluations[-1]['explanation']['parameters']['unknown_context']==50
    assert c.post(path+'/reevaluate',json=body,headers=h).status_code==409
    assert c.post(path+'/reevaluate',json={**body,'expected_revision':current()['revision']},headers=h).status_code==409
    audit=[r for r in c.get(path+'/timeline',headers=h).json() if r['kind']=='risk_reassessment']
    assert len(audit)==1 and audit[0]['resulting_revision']==audit[0]['previous_revision']+1
    assert audit[0]['author_id']==c.get('/api/auth/me',headers=h).json()['id'] and len(audit[0]['event_ids'])==3


def test_reassessment_race_and_actions_revision_contract(api,headers,batch):
    c,s,_=api;h=headers('administrador');iid,_,current,_=prepare_reopening(c,h,batch)
    path='/api/incidents/'+iid;revision=current()['revision'];barrier=Barrier(2)
    def post():
        barrier.wait(timeout=10)
        return c.post(path+'/reevaluate',json={'expected_revision':revision,'justification':'Concurrent fixture'},headers=h).status_code
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(lambda _:post(),range(2)))==[201,409]
    revision=current()['revision']
    assert c.post(path+'/actions',json={'description':'No revision'},headers=h).status_code==428
    assert c.post(path+'/actions',json={'description':'Stale revision','expected_revision':revision-1},headers=h).status_code==409
    barrier=Barrier(2)
    def action():
        barrier.wait(timeout=10)
        return c.post(path+'/actions',json={'description':'Concurrent comment','expected_revision':revision},headers=h).status_code
    with ThreadPoolExecutor(2) as pool: assert sorted(pool.map(lambda _:action(),range(2)))==[201,409]
    assert len(c.get(path+'/actions',headers=h).json())==1


def test_reassessment_rejects_unknown_parameters_and_allows_owner_analyst(api,headers,batch):
    c,s,_=api;h=headers('administrador');iid,_,current,_=prepare_reopening(c,h,batch)
    path='/api/incidents/'+iid
    with s.begin() as db:
        inc=db.get(Incident,iid);frozen=inc.risk_parameters;inc.risk_parameters=None
    body={'justification':'Explicit review','expected_revision':current()['revision']}
    assert c.post(path+'/reevaluate',json=body,headers=h).status_code==409
    with s.begin() as db: db.get(Incident,iid).risk_parameters='{"algorithm_version":"unknown"}'
    assert c.post(path+'/reevaluate',json=body,headers=h).status_code==409
    with s.begin() as db:
        db.get(Incident,iid).risk_parameters=frozen
        uid=db.scalar(select(User.id).where(User.role=='analista'))
    assert c.patch(path+'/assignment',json={'assigned_to_id':uid,'justification':'Analyst review','expected_revision':current()['revision']},headers=h).status_code==200
    body['expected_revision']=current()['revision']
    assert c.post(path+'/reevaluate',json=body,headers=headers('analista')).status_code==201


@pytest.mark.parametrize('api',['0007'],indirect=True)
def test_0008_preserves_every_existing_table(api):
    _,s,config=api
    with s.begin() as db:
        uid=db.scalar(select(User.id))
        db.execute(text("INSERT INTO incidents(id,correlation_key,event_type,status,score,priority,explanation,created_at) VALUES('legacy08','legacy08','dos','Cerrado',80,'Crítica','{}',CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO evaluation_datasets(id,author_id,name,data_kind,configuration,feature_hash,created_at) VALUES('d08',:uid,'old','synthetic','{}','old',CURRENT_TIMESTAMP)"),{'uid':uid})
        db.execute(text("INSERT INTO ml_runs(id,dataset_id,author_id,status,configuration,artifacts,results,created_at) VALUES('m08','d08',:uid,'completed','{}','{}','{}',CURRENT_TIMESTAMP)"),{'uid':uid})
        from sqlalchemy import inspect
        tables=sorted(t for t in inspect(db.connection()).get_table_names() if t!='alembic_version')
        before={t:db.execute(text(f'SELECT * FROM {t}')).mappings().all() for t in tables}
    command.upgrade(config,'head');command.upgrade(config,'head')
    with s() as db:
        for table in tables:
            rows=db.execute(text(f'SELECT * FROM {table}')).mappings().all()
            assert [{k:r[k] for k in before[table][0]} for r in rows]==before[table] if before[table] else rows==[]
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0009'


def test_offline_report_verifier(tmp_path):
    from app.verify_report import verify
    payload={'id':'synthetic-unit-test','value':0,'missing':None}
    path=tmp_path/'report.json'
    path.write_text(canonical({'payload':payload,'content_sha256':digest(payload)}),encoding='utf-8')
    assert verify(path)==digest(payload)
    payload['value']=1
    path.write_text(canonical({'payload':payload,'content_sha256':digest({'different':True})}),encoding='utf-8')
    with pytest.raises(ValueError): verify(path)
