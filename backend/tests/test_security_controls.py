import pytest
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import select, func
from app import main
from app.abuse import AbuseController, RequestGuard
from app.models import Event, EventEvidence, RiskEvaluation


def test_validation_does_not_echo_password(api):
    client,_,_=api
    marker='SYNTHETIC-SECRET-MARKER-'+('x'*150)
    response=client.post('/api/auth/login',json={'username':'missing','password':marker})
    assert response.status_code==422
    assert marker not in response.text


def test_login_rejects_unexpected_fields(api):
    client,_,_=api
    response=client.post('/api/auth/login',json={'username':'administrador','password':'test-password-123','role':'administrador'})
    assert response.status_code==422


def test_smartir_rejects_nul_without_changing_fingerprint_contract(api,headers,batch):
    client,_,_=api
    item={**batch['events'][0],'message':'synthetic\x00malformed'}
    response=client.post('/api/events/import',json={'events':[item]},headers=headers('analista'))
    assert response.status_code==422


def test_login_rate_retry_after_window_and_forwarded_header(api,monkeypatch):
    c,_,_=api;clock=[10.0]
    control=AbuseController(clock=lambda:clock[0],login_limit=3)
    monkeypatch.setattr(main.app.state,'abuse',control)
    for i in range(3):
        assert c.post('/api/auth/login',json={'username':'missing','password':'wrong'},headers={'X-Forwarded-For':f'203.0.113.{i}'}).status_code==401
    response=c.post('/api/auth/login',json={'username':'missing','password':'wrong'},headers={'X-Forwarded-For':'203.0.113.99'})
    assert response.status_code==429 and int(response.headers['Retry-After'])==60
    assert response.headers['Cache-Control']=='no-store'
    clock[0]+=60
    assert c.post('/api/auth/login',json={'username':'missing','password':'wrong'}).status_code==401


def test_limiter_capacity_and_nonblocking_slot_release():
    clock=[0.0];control=AbuseController(clock=lambda:clock[0],capacity=2)
    control.check('a',1);control.check('b',1)
    with pytest.raises(Exception) as full:control.check('c',1)
    assert full.value.status_code==429 and len(control._buckets)==2
    with control.work('compute'):
        with pytest.raises(Exception) as busy:
            with control.work('compute'):pass
        assert busy.value.status_code==429
    with pytest.raises(ValueError):
        with control.work('compute'):raise ValueError('synthetic failure')
    with control.work('compute'):pass
    clock[0]=61;control.check('c',1)
    assert len(control._buckets)==1


def test_costly_quotas_and_authorization_before_admission(api,headers,monkeypatch):
    c,_,_=api;admin=headers('administrador');observer=headers('observador')
    control=AbuseController();control.limits['compute']=1
    monkeypatch.setattr(main.app.state,'abuse',control)
    assert c.post('/api/evaluation/datasets/synthetic',json={'count':6},headers=observer).status_code==403
    assert c.post('/api/evaluation/datasets/synthetic',json={'count':6},headers=admin).status_code==201
    assert c.post('/api/evaluation/datasets/synthetic',json={'count':6},headers=admin).status_code==429
    with control.work('report'):
        with control.work('report'):
            r=c.post('/api/analytics/reports',json={},headers=admin)
            assert r.status_code==429 and r.headers['Retry-After']=='1'
    assert c.post('/api/analytics/reports',json={},headers=admin).status_code==201


def test_size_limits_malformed_json_and_safe_headers(api,headers):
    c,_,_=api;h=headers('administrador')
    assert c.post('/api/auth/login',content=b'x'*4097).status_code==413
    r=c.post('/api/events/import',content=b'{}',headers={**h,'Content-Length':'abc'})
    assert r.status_code==400
    assert c.post('/api/events/import',content=b'{bad',headers={**h,'Content-Type':'application/json'}).status_code==422
    assert c.post('/api/events/import',content=(b'x'*1024 for _ in range(5121)),headers=h).status_code==413
    for path in ('/health','/api/incidents','/api/auth/me'):
        r=c.get(path,headers=h)
        assert r.headers['X-Content-Type-Options']=='nosniff' and r.headers['X-Frame-Options']=='DENY'
        assert r.headers['Referrer-Policy']=='no-referrer'
        if path.startswith('/api/'):assert r.headers['Cache-Control']=='no-store'
    assert c.get('/api/auth/me',headers={'Authorization':'Bearer '+'x'*5000}).status_code==401
    assert c.get('/health',headers={'X-Oversized':'x'*17000}).status_code==431


@pytest.mark.parametrize('host',['evil.example','localhost/path?foo=','localhost#fragment','user@localhost','localhost:99999'])
def test_host_poisoning_is_rejected(api,host):
    c,_,_=api
    assert c.get('/health',headers={'Host':host}).status_code==400


def test_read_timeout_is_explicit_and_does_not_echo_body():
    sent=[]
    async def never_called(scope,receive,send):raise AssertionError('Body timeout must stop dispatch')
    class State:abuse=AbuseController()
    class App:state=State()
    async def receive():raise asyncio.TimeoutError()
    async def send(message):sent.append(message)
    scope={'type':'http','method':'POST','path':'/api/auth/login','headers':[(b'host',b'localhost')],'app':App(),'client':('127.0.0.1',1234)}
    asyncio.run(RequestGuard(never_called)(scope,receive,send))
    assert sent[0]['status']==408


def test_bulk_same_batch_and_concurrent_duplicates_preserve_evidence(api,headers):
    c,s,_=api;h=headers('analista')
    row=b'{"timestamp":"2026-01-01T00:00:00Z","event_type":"alert","src_ip":"192.0.2.1","dest_ip":"192.0.2.2","alert":{"category":"network-scan","severity":2,"signature":"SYNTHETIC DUPLICATE"}}\n'
    barrier=Barrier(2)
    def post():
        barrier.wait(timeout=10)
        return c.post('/api/events/import/eve',content=row*3,headers={**h,'Content-Type':'application/x-ndjson'})
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda _:post(),range(2)))
    assert all(r.status_code==200 for r in responses)
    assert sum(r.json()['imported'] for r in responses)==1
    assert sum(r.json()['duplicates'] for r in responses)==5
    with s() as db:
        assert db.scalar(select(func.count()).select_from(Event))==1
        assert db.scalar(select(func.count()).select_from(EventEvidence))==6
        assert db.scalar(select(func.count()).select_from(RiskEvaluation))==1


def test_legacy_pagination_and_statistics_remain_consistent(api,headers,batch):
    c,_,_=api;h=headers('analista')
    c.post('/api/events/import',json=batch,headers=h)
    first=c.get('/api/incidents?limit=2',headers=h).json()
    second=c.get('/api/incidents?limit=2&offset=2',headers=h).json()
    assert len(first)==len(second)==2 and not {r['id'] for r in first}&{r['id'] for r in second}
    assert c.get('/api/stats',headers=h).json()['incidents']==4
    assert c.get('/api/incidents?limit=1001',headers=h).status_code==422
    iid=first[0]['id']
    detail=c.get('/api/incidents/'+iid+'?events_limit=1',headers=h).json()
    assert detail['events_limit']==1 and len(detail['events'])<=1
    assert c.get('/api/incidents/'+iid+'?events_limit=501',headers=h).status_code==422


def test_synthetic_generator_and_percentiles_are_reproducible():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'benchmarks'))
    from synthetic_events import batches,fingerprint
    from run_load import percentiles
    assert fingerprint(100,202609)==fingerprint(100,202609)
    assert fingerprint(100,202609)!=fingerprint(100,202610)
    assert len(list(batches(10000)))==10 and all(block.count(b'\n')<=1000 for block in batches(10000))
    assert percentiles([1,2,3,4,5])['p95']==pytest.approx(4.8)


def test_report_aggregation_does_not_hold_mutation_lock(api,headers,monkeypatch):
    from app import analytics, lifecycle
    c,_,_=api;h=headers('administrador');calls=[]
    original_lock=lifecycle.mutation_lock;original_dashboard=analytics.dashboard
    def lock(db):calls.append('lock');return original_lock(db)
    def aggregate(db,q):
        assert calls==[]
        return original_dashboard(db,q)
    monkeypatch.setattr(lifecycle,'mutation_lock',lock)
    monkeypatch.setattr(analytics,'dashboard',aggregate)
    assert c.post('/api/analytics/reports',json={},headers=h).status_code==201
    assert calls==['lock']


def test_report_publication_rechecks_inactive_author(api,headers,monkeypatch):
    from app import lifecycle
    from app.models import User,AnalyticsReport
    c,s,_=api;h=headers('administrador');uid=c.get('/api/auth/me',headers=h).json()['id']
    original=lifecycle.mutation_lock
    def deactivate_before_publish(db):
        with s.begin() as other:other.get(User,uid).active=False
        return original(db)
    monkeypatch.setattr(lifecycle,'mutation_lock',deactivate_before_publish)
    assert c.post('/api/analytics/reports',json={},headers=h).status_code==401
    with s() as db:assert db.scalar(select(func.count()).select_from(AnalyticsReport))==0
