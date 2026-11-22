"""Bounded synthetic files and mocked/isolated API only; never use the operational DB."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import email.utils
import httpx
import pytest
from sqlalchemy import select, func, text, inspect
from alembic import command

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'agent'))
from smartir_agent.config import Config, AgentError, credentials, MAX_LINE_BYTES
from smartir_agent.store import Store
from smartir_agent.tailer import Tailer
from smartir_agent.runner import Agent
from smartir_agent.transport import Transport, Retry, retry_after, validate_report
from smartir_agent.synthetic import line
from app.models import User, Event, EventEvidence


def config(tmp_path, **kwargs):
    source=tmp_path/'eve.json'
    if not source.exists(): source.write_bytes(b'')
    return Config(source=source,state_dir=tmp_path/'state',rotate_wait_seconds=0,**kwargs)


def report(batch, **changes):
    return {'import_id':str(uuid4()),'imported':batch['records'],'duplicates':0,'discarded':0,
            'processed':batch['records'],'batches':1,'bytes_received':len(batch['body']), 'unknown':0,
            'errors':[],'errors_omitted':0,'discard_reasons':{},'complete':True,**changes}


class Accept:
    actor_id='isolated-test-actor'
    def __init__(self): self.bodies=[]
    def send(self,batch):self.bodies.append(batch['body']);return report(batch)


def test_incremental_incomplete_blank_and_documentary_order(tmp_path):
    cfg=config(tmp_path,batch_lines=2);cfg.source.write_bytes(line(0)+b'\n'+line(1)[:-3])
    store=Store(cfg);transport=Accept();agent=Agent(store,transport)
    try:
        agent.step();first=store.source()['offset']
        assert first==len(line(0))+1 and store.source()['line']==2
        agent.step();assert store.source()['offset']==first
        with cfg.source.open('ab') as f:f.write(line(1)[-3:]+line(2))
        agent.step();assert transport.bodies==[line(0)+b'\n',line(1)+line(2)]
        assert store.source()['offset']==cfg.source.stat().st_size and store.source()['line']==4
        assert [r[0] for r in store.db.execute('SELECT status FROM batches ORDER BY seq')]==['accepted','accepted']
    finally:store.close()


def test_durable_spool_restart_and_exclusive_reader(tmp_path):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0)+line(1));store=Store(cfg)
    pending=Tailer(store).poll()
    assert store.source()['offset']==0
    with pytest.raises(AgentError,match='checkpoint_already_locked'):Store(cfg)
    store.close()
    # Original can disappear after spooling: exact durable bytes are still delivered.
    cfg.source.rename(tmp_path/'retained.eve')
    other=Store(cfg);accept=Accept()
    try:
        assert other.pending()['id']==pending['id']
        Agent(other,accept).step();assert accept.bodies==[line(0)+line(1)]
        assert other.source()['offset']==len(line(0)+line(1))
    finally:other.close()


def test_rotation_multiple_generations_restart_and_late_growth(tmp_path):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));store=Store(cfg);accept=Accept()
    Agent(store,accept).step();store.close()
    cfg.source.rename(tmp_path/'eve.json.2');(tmp_path/'eve.json.1').write_bytes(line(1));cfg.source.write_bytes(line(2))
    store=Store(cfg);agent=Agent(store,accept)
    try:
        for _ in range(5):agent.step()
        assert accept.bodies==[line(0),line(1),line(2)]
        assert store.db.execute('SELECT count(*) FROM sources').fetchone()[0]==3
        with (tmp_path/'eve.json.2').open('ab') as f:f.write(line(3))
        with pytest.raises(AgentError,match='late_retired_growth'):agent.step()
        assert store.source()['offset']==len(line(2))
    finally:store.close()


@pytest.mark.parametrize('mode',['smaller','same_size_rewrite','missing_rotation','oversized','rotated_incomplete'])
def test_source_gaps_block_without_advancing(tmp_path,mode):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));store=Store(cfg);agent=Agent(store,Accept());agent.step()
    previous=store.source()['offset']
    if mode=='smaller':cfg.source.write_bytes(b'{')
    elif mode=='same_size_rewrite':cfg.source.write_bytes(b'x'*previous)
    elif mode=='missing_rotation':cfg.source.rename(tmp_path/'outside-retention.json');cfg.source.write_bytes(line(1))
    elif mode=='oversized':
        with cfg.source.open('ab') as f:f.write(b'x'*(MAX_LINE_BYTES+1)+b'\n')
    else:
        with cfg.source.open('ab') as f:f.write(b'{incomplete')
        cfg.source.rename(tmp_path/'eve.json.1');cfg.source.write_bytes(line(1))
    try:
        with pytest.raises(AgentError):agent.step()
        assert store.source()['offset']==previous and store.get('blocked')
        assert store.db.execute('SELECT code FROM audit ORDER BY seq DESC LIMIT 1').fetchone()[0]==store.get('blocked')
    finally:store.close()


def test_binding_and_explicit_audited_reset(tmp_path):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));s=Store(cfg);Agent(s,Accept()).step()
    cfg.source.write_bytes(line(1)[:10])
    with pytest.raises(AgentError):Agent(s,Accept()).step()
    with pytest.raises(AgentError,match='explicit_source_reset_required'):s.resume()
    s.resume(accept_reset=True)
    assert s.source()['offset']==0 and not s.get('blocked')
    cfg.source.write_bytes(line(1)+line(2)+line(3))
    Agent(s,Accept()).step();Agent(s,Accept()).step()
    assert s.source()['offset']==cfg.source.stat().st_size
    assert s.db.execute("SELECT count(*) FROM audit WHERE code='operator_source_reset_gap_possible'").fetchone()[0]==1
    s.close()
    with pytest.raises(AgentError,match='checkpoint_binding_mismatch'):Store(config(tmp_path,sensor_id='other'))


def test_foreign_database_never_modified(tmp_path):
    import sqlite3
    cfg=config(tmp_path);cfg.state_dir.mkdir(mode=0o700)
    target=cfg.state_dir/'state.db'
    with sqlite3.connect(target) as db:db.execute('CREATE TABLE unrelated(value TEXT)')
    previous=target.read_bytes()
    with pytest.raises(AgentError,match='foreign_or_invalid_state_database'):Store(cfg)
    assert target.read_bytes()==previous


def test_corrupt_spool_not_sent_or_skipped(tmp_path):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));s=Store(cfg);transport=Accept()
    try:
        Tailer(s).poll()
        with s.db:s.db.execute("UPDATE batches SET body=?",(b'corrupted\n',))
        with pytest.raises(AgentError,match='spool_integrity_failure'):Agent(s,transport).step()
        assert not transport.bodies and s.source()['offset']==0 and s.get('blocked')=='spool_integrity_failure'
    finally:s.close()


def test_compressed_and_large_responses_rejected(tmp_path):
    cfg=config(tmp_path)
    for encoding in ('gzip','huge'):
        t=mock_transport(cfg,lambda req:httpx.Response(200,stream=httpx.ByteStream(b'x'*(128*1024+1 if encoding=='huge' else 10)),
            headers={'Content-Encoding':'identity' if encoding=='huge' else 'gzip'}))
        try:
            with pytest.raises(AgentError):t.authenticate()
        finally:t.close()


def test_failed_login_and_overprivileged_account_are_not_accepted(tmp_path):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0))
    for error in ('invalid_credentials','not_scoped'):
        calls=[]
        def handler(req):
            calls.append(req.url.path)
            if error=='invalid_credentials':return httpx.Response(401)
            response=auth_response(req)
            if req.url.path=='/api/auth/me':return httpx.Response(200,json={**response.json(),'eve_only':False})
            return response
        transport=mock_transport(cfg,handler)
        try:
            with pytest.raises(AgentError):transport.authenticate()
            assert calls.count('/api/auth/login')==1 and transport.token is None
        finally:transport.close()


@pytest.mark.parametrize('url',['http://example.com','http://0.0.0.0:8000','http://api:8000',
    'https://example.com','http://user:secret@127.0.0.1:8000','http://127.0.0.1/api','http://127.0.0.1?token=secret','file:///tmp/api'])
def test_unsafe_origins_rejected(tmp_path,url):
    with pytest.raises(AgentError,match='unsafe_api_origin'):config(tmp_path,api_url=url)


def test_tls_and_proxy_defaults_and_credentials(tmp_path,monkeypatch):
    cfg=config(tmp_path,api_url='https://example.com',allow_remote_https=True)
    t=Transport(cfg)
    try:
        assert t.client.follow_redirects is False and t.client._trust_env is False
        context=t.client._transport._pool._ssl_context
        import ssl
        assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
    finally:t.close()
    secret=tmp_path/'password';secret.write_text(secrets.token_urlsafe(24),encoding='utf-8');secret.chmod(0o600)
    monkeypatch.setenv('SMARTIR_AGENT_USERNAME','service-test');monkeypatch.setenv('SMARTIR_AGENT_PASSWORD_FILE',str(secret))
    monkeypatch.delenv('SMARTIR_AGENT_PASSWORD',raising=False)
    assert credentials()[1]==secret.read_text()
    monkeypatch.setenv('SMARTIR_AGENT_PASSWORD','ambiguous')
    with pytest.raises(AgentError,match='ambiguous_credentials'):credentials()


def mock_transport(cfg, handler):
    return Transport(cfg,client=httpx.Client(base_url=cfg.api_url,transport=httpx.MockTransport(handler)),
                     credential_provider=lambda:('synthetic-service',secrets.token_urlsafe(24)))


def auth_response(request):
    if request.url.path=='/api/auth/login':return httpx.Response(200,json={'access_token':'SYNTHETIC-NOT-A-JWT','token_type':'bearer','expires_in':900})
    if request.url.path=='/api/auth/me':return httpx.Response(200,json={'id':str(uuid4()),'active':True,'role':'analista','eve_only':True})


@pytest.mark.parametrize('status',[400,401,403,413,422,302])
def test_permanent_http_errors_retain_spool_no_automatic_retry(tmp_path,status):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));calls=[]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path!='/api/events/import/eve':return auth_response(req)
        return httpx.Response(status,json={'detail':'Sensitive body must not be logged'})
    s=Store(cfg);t=mock_transport(cfg,handler);agent=Agent(s,t)
    try:
        with pytest.raises(AgentError,match='http_'+str(status)):agent.step()
        assert s.source()['offset']==0 and s.pending()['body']==line(0)
        n=len(calls)
        with pytest.raises(AgentError,match='checkpoint_blocked'):agent.step()
        assert len(calls)==n
        assert calls.count('/api/events/import/eve')==(2 if status==401 else 1)
    finally:t.close();s.close()


@pytest.mark.parametrize('status',[429,503])
def test_transient_deadlines_survive_restart_and_recover(tmp_path,status,monkeypatch):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));clock=[1_800_000_000.0]
    monkeypatch.setattr('time.time',lambda:clock[0]);calls=[];s=Store(cfg)
    def handler(req):
        if req.url.path!='/api/events/import/eve':return auth_response(req)
        calls.append(1)
        if len(calls)==1:return httpx.Response(status,headers={'Retry-After':'120'})
        return httpx.Response(200,json=report(s.pending()))
    t=mock_transport(cfg,handler)
    try:
        assert Agent(s,t).step()>=120 and s.source()['offset']==0
        s.close();s=Store(cfg)
        assert Agent(s,t).step()>=120 and len(calls)==1
        clock[0]+=121;Agent(s,t).step()
        assert len(calls)==2 and s.source()['offset']==len(line(0))
    finally:t.close();s.close()


def test_retry_after_date_and_oversize():
    now=datetime.now(timezone.utc).replace(microsecond=0)
    assert retry_after(email.utils.format_datetime(now+timedelta(seconds=90)),now.timestamp())==90
    assert retry_after('nonsense') is None and retry_after('0')==1
    with pytest.raises(AgentError,match='retry_after_excessive'):retry_after(str(366*86400))


def test_token_expiry_renewal_and_single_401_reauthentication(tmp_path):
    cfg=config(tmp_path);cfg.source.write_bytes(line(0));s=Store(cfg);batch=Tailer(s).poll();calls=[];eve=[0]
    def handler(req):
        calls.append(req.url.path)
        if req.url.path!='/api/events/import/eve':return auth_response(req)
        eve[0]+=1
        if eve[0]==1:return httpx.Response(401)
        return httpx.Response(200,json=report(batch))
    t=mock_transport(cfg,handler)
    try:
        Agent(s,t).step();assert calls.count('/api/auth/login')==2
        t.expiry=0;t.send(batch);assert calls.count('/api/auth/login')==3
        codes={r[0] for r in s.db.execute('SELECT code FROM audit')}
        assert {'jwt_obtain','eve_request_started','http_401_reauthenticate','jwt_renewal_due'}.issubset(codes)
        assert not any('SYNTHETIC-NOT-A-JWT' in r[0] for r in s.db.execute('SELECT details FROM audit'))
    finally:t.close();s.close()


def test_unverifiable_report_never_advances_and_bounds(tmp_path):
    cfg=config(tmp_path,batch_lines=100,batch_bytes=65537)
    cfg.source.write_bytes(b''.join(line(i) for i in range(300)));s=Store(cfg);batch=Tailer(s).poll()
    try:
        assert batch['records']==100 and len(batch['body'])<=cfg.batch_bytes
        for changes in ({'complete':False},{'bytes_received':0},{'errors_omitted':1},{'processed':99},{'discarded':1},{'imported':True}):
            with pytest.raises(AgentError,match='unverifiable_acceptance'):validate_report(report(batch,**changes),batch)
        assert s.source()['offset']==0
    finally:s.close()


def service(api,headers):
    c,_,_=api;password=secrets.token_urlsafe(24)
    r=c.post('/api/users',headers=headers('administrador'),json={'username':'eve-service','password':password,'role':'analista','eve_only':True})
    assert r.status_code==201
    return ('eve-service',password),r.json()['id']


def test_api_service_least_privilege_inactive_and_assignment_guard(api,headers,batch):
    c,s,_=api;creds,uid=service(api,headers)
    token=c.post('/api/auth/login',json=dict(zip(('username','password'),creds))).json()['access_token'];h={'Authorization':'Bearer '+token}
    assert c.get('/api/auth/me',headers=h).json()['eve_only'] is True
    for method,path,body in [('GET','/api/incidents',None),('GET','/api/users',None),('GET','/api/evaluation/datasets',None),
        ('GET','/api/ml/versions',None),('GET','/api/analytics/reports',None),('POST','/api/events/import',batch),
        ('POST','/api/ml/train',{}),('GET','/api/operations/metrics',None),('GET','/api/assignees',None)]:
        assert c.request(method,path,headers=h,json=body).status_code==403
    eve=c.post('/api/events/import/eve?sensor_id=iter11',headers={**h,'Content-Type':'application/x-ndjson'},content=line(0))
    assert eve.status_code==200 and eve.json()['imported']==1
    admin=headers('administrador')
    assert uid not in [u['id'] for u in c.get('/api/assignees',headers=admin).json()]
    iid=c.get('/api/incidents',headers=admin).json()[0]
    assert c.patch('/api/incidents/'+iid['id']+'/assignment',headers=admin,json={'assigned_to_id':uid,'expected_revision':iid['revision'],'justification':'Not eligible'}).status_code==409
    assert c.patch('/api/users/'+uid,headers=admin,json={'role':'administrador'}).status_code==422
    assert c.patch('/api/users/'+uid,headers=admin,json={'active':False}).status_code==200
    assert c.get('/api/auth/me',headers=h).status_code==401


def test_real_adapter_rejected_lines_quarantined_order_and_legacy_compatibility(api,headers,tmp_path,batch):
    c,session,_=api;creds,_=service(api,headers);cfg=config(tmp_path,batch_lines=3,api_url='http://localhost')
    original=line(0)+b'{invalid\n'+line(1)+b'{"event_type":"flow"}\n'+line(2)
    cfg.source.write_bytes(original);s=Store(cfg);t=Transport(cfg,client=c,credential_provider=lambda:creds)
    try:
        a=Agent(s,t);a.step();a.step()
        assert s.source()['offset']==len(original) and s.source()['line']==5
        rows=s.db.execute('SELECT * FROM batches ORDER BY seq').fetchall()
        assert rows[0]['body']==line(0)+b'{invalid\n'+line(1) and rows[1]['body']==b'{"event_type":"flow"}\n'+line(2)
        assert json.loads(rows[0]['report'])['errors'][0]['line']==2
        with session() as db:
            assert db.scalar(select(func.count()).select_from(Event))==3
            assert db.scalar(select(func.count()).select_from(EventEvidence))==3
        h=headers('analista');assert c.post('/api/events/import',headers=h,json=batch).status_code==200
    finally:s.close()


def test_exact_eve_line_limit_is_accepted_by_agent_and_adapter(api,headers,tmp_path):
    c,session,_=api;creds,_=service(api,headers);cfg=config(tmp_path,api_url='http://localhost')
    item=json.loads(line(0));item['padding']=''
    overhead=len(json.dumps(item,separators=(',',':')).encode())
    item['padding']='x'*(MAX_LINE_BYTES-overhead)
    raw=json.dumps(item,separators=(',',':')).encode()+b'\n'
    assert len(raw)==MAX_LINE_BYTES+1
    cfg.source.write_bytes(raw);s=Store(cfg);t=Transport(cfg,client=c,credential_provider=lambda:creds)
    try:
        Agent(s,t).step();assert s.source()['offset']==len(raw)
        with session() as db:assert db.scalar(select(func.count()).select_from(Event))==1
    finally:s.close()


def test_lost_http_response_replays_exact_pending_bytes_server_deduplicates(api,headers,tmp_path,monkeypatch):
    c,session,_=api;creds,_=service(api,headers);cfg=config(tmp_path,api_url='http://localhost');cfg.source.write_bytes(line(0)+line(1))
    s=Store(cfg);lost=[False];bodies=[];clock=[1_800_000_000.0];monkeypatch.setattr('time.time',lambda:clock[0])
    def handler(req):
        response=c.request(req.method,req.url.raw_path.decode(),headers=dict(req.headers),content=req.content)
        if req.url.path=='/api/events/import/eve':
            bodies.append(req.content)
            if not lost[0]:lost[0]=True;raise httpx.ReadError('Never logged sensitive body',request=req)
        return httpx.Response(response.status_code,headers=response.headers,content=response.content)
    t=Transport(cfg,client=httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(handler)),credential_provider=lambda:creds)
    try:
        delay=Agent(s,t).step();assert s.source()['offset']==0
        s.close();s=Store(cfg);clock[0]+=delay+1;Agent(s,t).step()
        assert bodies==[line(0)+line(1)]*2 and s.source()['offset']==cfg.source.stat().st_size
        r=json.loads(s.db.execute('SELECT report FROM batches').fetchone()[0]);assert r['duplicates']==2 and r['imported']==0
        with session() as db:
            assert db.scalar(select(func.count()).select_from(Event))==2
            assert db.scalar(select(func.count()).select_from(EventEvidence))==4
    finally:t.close();s.close()


@pytest.mark.parametrize('api',['0008'],indirect=True)
def test_0009_is_additive_preserves_all_old_columns_and_users(api):
    _,s,cfg=api
    with s() as db:
        tables=inspect(db.connection()).get_table_names()
        before={t:[dict(r) for r in db.execute(text(f'SELECT * FROM {t}')).mappings()] for t in tables if t!='alembic_version'}
    command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    with s() as db:
        for table,expected in before.items():
            rows=db.execute(text(f'SELECT * FROM {table}')).mappings().all()
            assert [{k:r[k] for k in expected[0]} for r in rows]==expected if expected else rows==[]
        assert all(u.eve_only is False for u in db.scalars(select(User)))
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0009'
