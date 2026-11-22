from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
import json
import pytest
from alembic import command
from sqlalchemy import select, text
from app import lifecycle, ingestion
from app.models import Incident, IncidentHistory, AssignmentHistory, RiskEvaluation, User


def create(client,h,batch):
    assert client.post('/api/events/import',json={'events':[batch['events'][0]]},headers=h).status_code==200
    return client.get('/api/incidents',headers=h).json()[0]['id']


def current(client,h,iid):return client.get('/api/incidents/'+iid,headers=h).json()


def assign(client,h,iid,uid,revision=None):
    if revision is None:revision=current(client,h,iid)['revision']
    return client.patch(f'/api/incidents/{iid}/assignment',json={'assigned_to_id':uid,'justification':'Documented assignment','expected_revision':revision},headers=h)


def transition(client,h,iid,state,revision=None):
    if revision is None:revision=current(client,h,iid)['revision']
    return client.patch(f'/api/incidents/{iid}/status',json={'status':state,'justification':'Documented transition or reopening','expected_revision':revision},headers=h)


def close(client,h,iid,uid):
    assert assign(client,h,iid,uid).status_code==200
    for s in ('En análisis','En respuesta','Resuelto','Cerrado'):
        assert transition(client,h,iid,s).status_code==200


def test_assignment_reassignment_withdraw_and_real_author(api,headers,batch):
    client,session,_=api
    admin,analyst=headers('administrador'),headers('analista')
    aid=client.get('/api/auth/me',headers=admin).json()['id']
    uid=client.get('/api/auth/me',headers=analyst).json()['id']
    iid=create(client,admin,batch)
    assert assign(client,analyst,iid,aid).status_code==403
    assert assign(client,analyst,iid,uid).json()['status']=='Asignado'
    assert assign(client,analyst,iid,aid).status_code==200
    assert assign(client,analyst,iid,uid).status_code==403
    assert assign(client,admin,iid,None).json()['status']=='Nuevo'
    rows=client.get(f'/api/incidents/{iid}/timeline',headers=admin).json()
    assignments=[r for r in rows if r['kind']=='assignment']
    assert len(assignments)==3 and assignments[0]['author']=='analista'
    assert assignments[0]['author_id']==uid and assignments[0]['assigned_user_id']==uid
    assert assignments[1]['previous_assignee']=='analista' and assignments[1]['assignee']=='administrador'
    with session() as db:
        assert len(db.scalars(select(AssignmentHistory).where(AssignmentHistory.incident_id==iid)).all())==3


def test_ineligible_users_and_user_role_race_guard(api,headers,batch):
    client,session,_=api
    h=headers('administrador');iid=create(client,h,batch)
    users=client.get('/api/users',headers=h).json()
    observer=next(u['id'] for u in users if u['role']=='observador')
    analyst=next(u['id'] for u in users if u['role']=='analista')
    assert assign(client,h,iid,observer).status_code==409
    assert client.patch('/api/users/'+analyst,json={'active':False},headers=h).status_code==200
    assert assign(client,h,iid,analyst).status_code==409
    assert assign(client,h,iid,'missing').status_code==409
    client.patch('/api/users/'+analyst,json={'active':True},headers=h)
    assert assign(client,h,iid,analyst).status_code==200
    for patch in ({'active':False},{'role':'observador'}):
        assert client.patch('/api/users/'+analyst,json=patch,headers=h).status_code==409
    assert client.patch('/api/users/'+analyst,json={'active':True},headers=h).status_code==200


@pytest.mark.parametrize('target',['Resuelto','Cerrado','En respuesta','En análisis'])
def test_new_incident_cannot_skip_assignment(api,headers,batch,target):
    client,_,_=api;h=headers('administrador');iid=create(client,h,batch)
    assert transition(client,h,iid,target).status_code==409
    assert current(client,h,iid)['status']=='Nuevo'


def test_machine_rollbacks_reopen_and_assignment_requirements(api,headers,batch):
    client,_,_=api
    a,h=headers('administrador'),headers('analista')
    uid=client.get('/api/auth/me',headers=h).json()['id'];iid=create(client,a,batch)
    assert assign(client,h,iid,uid).status_code==200
    assert transition(client,h,iid,'En análisis').status_code==200
    assert assign(client,h,iid,None).status_code==409
    assert transition(client,h,iid,'Asignado').status_code==200
    assert transition(client,h,iid,'En análisis').status_code==200
    assert transition(client,h,iid,'En respuesta').status_code==200
    assert transition(client,h,iid,'En análisis').status_code==200
    assert transition(client,h,iid,'En respuesta').status_code==200
    assert transition(client,h,iid,'Resuelto').status_code==200
    assert transition(client,h,iid,'En análisis').status_code==200
    assert client.get(f'/api/incidents/{iid}/lifecycle',headers=h).json()['cycle_number']==2
    for state in ('En respuesta','Resuelto','Cerrado'):assert transition(client,h,iid,state).status_code==200
    assert transition(client,h,iid,'En análisis').status_code==403
    assert transition(client,a,iid,'En análisis').status_code==200
    assert client.get(f'/api/incidents/{iid}/lifecycle',headers=h).json()['cycle_number']==3


def test_preconditions_and_observer_read_only(api,headers,batch):
    client,_,_=api;a=headers('administrador');o=headers('observador');iid=create(client,a,batch)
    assert client.patch(f'/api/incidents/{iid}/status',json={'status':'Asignado','justification':'reason'},headers=a).status_code==428
    assert client.patch(f'/api/incidents/{iid}/assignment',json={'assigned_to_id':None,'justification':'reason'},headers=a).status_code==428
    assert client.patch(f'/api/incidents/{iid}/assignment',json={'assigned_to_id':None,'justification':'\u0000','expected_revision':1},headers=a).status_code==422
    assert client.patch(f'/api/incidents/{iid}/assignment',json={'assigned_to_id':'','justification':'reason','expected_revision':1},headers=a).status_code==422
    for suffix in ('lifecycle','timeline','history','actions'):
        assert client.get(f'/api/incidents/{iid}/{suffix}',headers=o).status_code==200
    uid=client.get('/api/auth/me',headers=a).json()['id']
    assert assign(client,o,iid,uid).status_code==403
    assert transition(client,o,iid,'En análisis').status_code==403
    assert client.post(f'/api/incidents/{iid}/actions',json={'description':'comment'},headers=o).status_code==403
    assert client.get('/api/operations/metrics',headers=o).status_code==200
    assert client.get('/api/assignees',headers=o).status_code==200


def test_concurrent_assignment_has_single_winner(api,headers,batch):
    client,session,_=api;h=headers('administrador');iid=create(client,h,batch)
    people=client.get('/api/assignees',headers=h).json();revision=current(client,h,iid)['revision']
    barrier=Barrier(2)
    def attempt(uid):
        barrier.wait(timeout=10)
        return assign(client,h,iid,uid,revision).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt,[p['id'] for p in people]))
    assert sorted(results)==[200,409]
    with session() as db:
        assert len(db.scalars(select(AssignmentHistory).where(AssignmentHistory.incident_id==iid)).all())==1


def test_concurrent_transitions_no_lost_history(api,headers,batch):
    client,session,_=api;h=headers('administrador');uid=client.get('/api/auth/me',headers=h).json()['id']
    iid=create(client,h,batch);assign(client,h,iid,uid);transition(client,h,iid,'En análisis')
    revision=current(client,h,iid)['revision'];barrier=Barrier(2)
    def attempt(state):
        barrier.wait(timeout=10)
        return transition(client,h,iid,state,revision).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['Asignado','En respuesta']))
    assert sorted(results)==[200,409]
    with session() as db:
        assert len(db.scalars(select(IncidentHistory).where(IncidentHistory.incident_id==iid)).all())==4


def test_assignment_vs_deactivation_race_preserves_invariant(api,headers,batch):
    client,session,_=api;h=headers('administrador');iid=create(client,h,batch)
    uid=next(p['id'] for p in client.get('/api/assignees',headers=h).json() if p['role']=='analista')
    revision=current(client,h,iid)['revision'];barrier=Barrier(2)
    def assign_request():
        barrier.wait(timeout=10);return assign(client,h,iid,uid,revision).status_code
    def disable_request():
        barrier.wait(timeout=10);return client.patch('/api/users/'+uid,json={'active':False},headers=h).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(assign_request);b=pool.submit(disable_request);results=[a.result(),b.result()]
    assert sorted(results)==[200,409]
    with session() as db:
        inc=db.get(Incident,iid);person=db.get(User,uid)
        assert not (inc.assigned_to_id==uid and not person.active)


def test_import_vs_close_race_has_no_silent_closed_risk_update(api,headers,batch):
    client,_,_=api;h=headers('administrador');uid=client.get('/api/auth/me',headers=h).json()['id']
    iid=create(client,h,batch);assign(client,h,iid,uid)
    for state in ('En análisis','En respuesta','Resuelto'):transition(client,h,iid,state)
    before=current(client,h,iid);barrier=Barrier(2)
    late={**batch['events'][0],'message':'Concurrent late event','severity':100}
    def close_request():
        barrier.wait(timeout=10);return transition(client,h,iid,'Cerrado',before['revision']).status_code
    def import_request():
        barrier.wait(timeout=10);return client.post('/api/events/import',json={'events':[late]},headers=h).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(close_request);b=pool.submit(import_request);status,import_status=a.result(),b.result()
    assert import_status==200 and status in (200,409)
    after=current(client,h,iid)
    if status==200:
        assert after['status']=='Cerrado' and after['score']==before['score'] and after['needs_review']
    else:
        assert after['status']=='Resuelto' and not after['needs_review']


def test_recorded_times_first_latest_and_missing_evidence(api,headers,batch,monkeypatch):
    client,_,_=api;h=headers('administrador');uid=client.get('/api/auth/me',headers=h).json()['id']
    start=datetime(2026,11,21,20,tzinfo=timezone.utc)
    clock=[start];monkeypatch.setattr(lifecycle,'now',lambda:clock[0]);monkeypatch.setattr(ingestion,'now',lambda:clock[0])
    iid=create(client,h,batch)
    first=client.get(f'/api/incidents/{iid}/lifecycle',headers=h).json()
    assert all(m['status']=='No calculable' for m in first['metrics'].values())
    clock[0]+=timedelta(seconds=10);assign(client,h,iid,uid)
    clock[0]+=timedelta(seconds=10);transition(client,h,iid,'En análisis')
    clock[0]+=timedelta(seconds=10);transition(client,h,iid,'En respuesta')
    clock[0]+=timedelta(seconds=10);transition(client,h,iid,'Resuelto')
    clock[0]+=timedelta(seconds=10);transition(client,h,iid,'Cerrado')
    clock[0]+=timedelta(seconds=10);transition(client,h,iid,'En análisis')
    clock[0]+=timedelta(seconds=10);transition(client,h,iid,'En respuesta')
    result=client.get(f'/api/incidents/{iid}/lifecycle',headers=h).json()
    assert [result['metrics'][k]['value'] for k in ('time_to_assignment','time_to_response','time_to_resolution')]==[10,30,40]
    assert result['timestamps']['response']['first_recorded']!=result['timestamps']['response']['latest_recorded']
    assert result['current_cycle_metrics']['time_to_response']['value']==10
    assert result['current_cycle_metrics']['time_to_resolution']['value'] is None
    assert result['metrics']['mttd']['value'] is None and result['metrics']['mttr']['value'] is None


def test_temporal_evidence_revision_source_and_metrics(api,headers,batch):
    client,_,_=api;h=headers('administrador');iid=create(client,h,batch)
    data={'expected_revision':current(client,h,iid)['revision'],'source_kind':'synthetic',
        'evidence_reference':'unit-test-fixture, not real operations','review_note':'Synthetic verification fixture only',
        'occurred_at':'2025-12-31T18:00:00-06:00','detected_at':'2026-01-01T01:02:00+01:00','response_completed_at':'2026-01-01T00:10:00Z'}
    url=f'/api/incidents/{iid}/time-evidence'
    assert client.post(url,json=data,headers=headers('analista')).status_code==403
    assert client.post(url,json=data,headers=h).json()['metrics']['mttd']['value'] is None
    data.update(expected_revision=current(client,h,iid)['revision'],source_kind='operational')
    response=client.post(url,json=data,headers=h)
    assert response.status_code==201
    assert response.json()['metrics']['mttd']['value']==120 and response.json()['metrics']['mttr']['value']==480
    data.update(expected_revision=current(client,h,iid)['revision'],detected_at='2025-01-01T00:00:00Z')
    assert client.post(url,json=data,headers=h).status_code==422
    data['detected_at']='2026-01-01T00:02:00'
    assert client.post(url,json=data,headers=h).status_code==422
    assert len([i for i in client.get(f'/api/incidents/{iid}/timeline',headers=h).json() if i['kind']=='time_evidence'])==2


def test_actions_preserve_comments_and_category_constraints(api,headers,batch):
    client,_,_=api;h=headers('administrador');iid=create(client,h,batch);uid=client.get('/api/auth/me',headers=h).json()['id']
    path=f'/api/incidents/{iid}/actions'
    def post(data,headers):
        return client.post(path,json={**data,'expected_revision':current(client,headers,iid)['revision']},headers=headers)
    assert post({'description':'Existing compatible comment'},headers=headers('analista')).status_code==201
    assert post({'description':'Contain','category':'contencion'},headers=h).status_code==409
    assign(client,h,iid,uid);transition(client,h,iid,'En análisis');transition(client,h,iid,'En respuesta')
    assert post({'description':'Contain','category':'contencion'},headers=headers('analista')).status_code==403
    response=post({'description':'Containment record, no execution','category':'contencion'},headers=h)
    assert response.status_code==201 and response.json()['date_basis']=='recorded_at'
    declared=post({'description':'Declared timestamp','category':'verificacion','performed_at':'2026-01-01T05:00:00+05:00'},headers=h)
    assert declared.status_code==201
    assert client.get(path,headers=h).json()[-1]['performed_at']=='2026-01-01T00:00:00+00:00'
    assert post({'description':'Invalid','category':'command'},headers=h).status_code==422
    assert len(client.get(path,headers=h).json())==3


def test_closed_late_events_freeze_risk_and_signal_review(api,headers,batch):
    client,session,_=api;h=headers('administrador');uid=client.get('/api/auth/me',headers=h).json()['id']
    iid=create(client,h,batch);close(client,h,iid,uid)
    before=current(client,h,iid)
    evaluations=client.get(f'/api/incidents/{iid}/evaluations',headers=h).json()
    late={**batch['events'][0],'message':'Distinct late evidence','severity':100}
    assert client.post('/api/events/import',json={'events':[late]},headers=h).json()['imported']==1
    after=current(client,h,iid)
    assert after['status']=='Cerrado' and after['score']==before['score'] and after['explanation']==before['explanation']
    assert after['needs_review'] is True and len(after['events'])==len(before['events'])+1
    assert client.get(f'/api/incidents/{iid}/evaluations',headers=h).json()==evaluations
    assert transition(client,h,iid,'En análisis',before['revision']).status_code==409
    client.post('/api/events/import',json={'events':[late]},headers=h)
    timeline=client.get(f'/api/incidents/{iid}/timeline',headers=h).json()
    signals=[i for i in timeline if i['kind']=='review_signal'];assert len(signals)==1
    url=f'/api/incidents/{iid}/review-signals/{signals[0]["id"]}/acknowledge'
    assert client.post(url,json={'expected_revision':after['revision'],'justification':'Reviewed preserved evidence'},headers=h).status_code==201
    assert current(client,h,iid)['needs_review'] is False
    assert any(i['kind']=='review_acknowledgement' for i in client.get(f'/api/incidents/{iid}/timeline',headers=h).json())


@pytest.mark.parametrize('api',['0006'],indirect=True)
def test_0007_preserves_legacy_states_and_ml_data(api,headers):
    client,session,config=api
    with session.begin() as db:
        uid=db.execute(text('SELECT id FROM users LIMIT 1')).scalar()
        for i,state in enumerate(lifecycle.TRANSITIONS):
            db.execute(text("INSERT INTO incidents(id,correlation_key,event_type,status,score,priority,explanation,created_at) VALUES(:id,:key,'dos',:state,80,'Alta','{}',CURRENT_TIMESTAMP)"),{'id':str(i),'key':str(i),'state':state})
        db.execute(text("INSERT INTO evaluation_datasets(id,author_id,name,data_kind,configuration,feature_hash,created_at) VALUES('d',:uid,'old','synthetic','{}','old',CURRENT_TIMESTAMP)"),{'uid':uid})
        db.execute(text("INSERT INTO ml_runs(id,dataset_id,author_id,status,configuration,artifacts,results,created_at) VALUES('m','d',:uid,'completed','{}','{}','{}',CURRENT_TIMESTAMP)"),{'uid':uid})
        db.execute(text("INSERT INTO response_actions(id,incident_id,author_id,description,created_at) VALUES('a','1',:uid,'Original comment',CURRENT_TIMESTAMP)"),{'uid':uid})
        tables=['users','events','incidents','incident_history','response_actions','event_evidence','risk_evaluations','evaluation_datasets','evaluation_cases','evaluation_references','evaluation_event_links','experiments','ml_runs']
        before={t:db.execute(text(f'SELECT * FROM {t}')).mappings().all() for t in tables}
    command.upgrade(config,'head');command.upgrade(config,'head')
    with session() as db:
        for table in tables:
            rows=db.execute(text(f'SELECT * FROM {table}')).mappings().all()
            assert [{k:r[k] for k in before[table][0]} for r in rows]==before[table] if before[table] else rows==[]
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0009'
    h=headers('administrador')
    life=client.get('/api/incidents/5/lifecycle',headers=h).json()
    assert life['lifecycle_legacy'] is True and all(v['value'] is None for v in life['metrics'].values())
    assert client.get('/api/incidents/1/actions',headers=h).json()[0]['category']=='legacy_unclassified'
