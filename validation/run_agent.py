"""Real TCP + independent agent processes, only fresh UUID databases and synthetic files."""
import argparse
import csv
import hashlib
import json
import os
import platform
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
import httpx
from sqlalchemy import create_engine, text
from .isolated import Isolated, ROOT

sys.path.insert(0,str(ROOT/'agent'))
from smartir_agent.synthetic import line


def wait_until(predicate, seconds=30):
    start=time.monotonic()
    while time.monotonic()-start < seconds:
        try:
            if predicate():return time.monotonic()-start
        except (sqlite3.OperationalError, FileNotFoundError):pass
        time.sleep(.05)
    raise RuntimeError('Isolated validation condition timed out; no response bodies or secrets exported')


def run(dialect, label, iteration='11'):
    output=ROOT/'docs/resultados'/f'iter{iteration}_agent_http_{dialect}_{label}.json'
    if output.exists() or output.with_suffix('.csv').exists():raise RuntimeError('Evidence exists; use another label')
    instance=Isolated(dialect)
    started=time.perf_counter();process=None;log=None
    with instance.running(), httpx.Client(base_url=instance.base_url,trust_env=False,timeout=30) as client:
        engine=create_engine(instance.url)
        source=instance.directory/'eve.json';state=instance.directory/'agent-state';checkpoint=state/'state.db'
        source.write_bytes(b''.join(line(n) for n in range(6))+line(6)[:50])
        username,password=instance.credentials['administrador']
        token=client.post('/api/auth/login',json={'username':username,'password':password}).json()['access_token']
        service_password=secrets.token_urlsafe(24)
        user=client.post('/api/users',headers={'Authorization':'Bearer '+token},json={
            'username':'iter11-isolated-service','password':service_password,'role':'analista','eve_only':True})
        assert user.status_code==201
        uid=user.json()['id']
        env={**instance.environment,'PYTHONPATH':str(ROOT/'agent'),'SMARTIR_AGENT_USERNAME':'iter11-isolated-service',
             'SMARTIR_AGENT_PASSWORD':service_password,'SMARTIR_AGENT_PASSWORD_FILE':''}
        def start_agent():
            nonlocal process,log
            log=(instance.directory/'agent.log').open('ab')
            process=subprocess.Popen([sys.executable,'-m','smartir_agent','--file',str(source),'--state-dir',str(state),
                '--api-url',instance.base_url,'--sensor','iter11-live','--poll','.1','--rotate-wait','.2','--batch-lines','3'],
                cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def stop_agent():
            nonlocal process,log
            if process:
                process.terminate();process.wait(timeout=10);process=None
            if log:log.close();log=None
        def events():
            with engine.connect() as db:return db.scalar(text('SELECT count(*) FROM events'))
        def checkpoint_query(query):
            if not checkpoint.exists():return None
            with sqlite3.connect(checkpoint) as db:return db.execute(query).fetchone()[0]
        phases=[]
        try:
            start_agent()
            phases.append({'phase':'initial_six_incomplete_wait','seconds':wait_until(lambda:events()==6 and checkpoint_query("SELECT count(*) FROM batches WHERE status='accepted'")==2)})
            second=subprocess.run([sys.executable,'-m','smartir_agent','--file',str(source),'--state-dir',str(state),
                '--api-url',instance.base_url,'--sensor','iter11-live','--once'],cwd=ROOT,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            assert second.returncode==2 and b'checkpoint_already_locked' in second.stdout
            assert checkpoint_query('SELECT offset FROM sources WHERE current=1')==sum(len(line(n)) for n in range(6))
            stop_agent()
            with source.open('ab') as f:f.write(line(6)[50:]+line(7)+line(8))
            start_agent()
            phases.append({'phase':'restart_remaining_three','seconds':wait_until(lambda:events()==9 and checkpoint_query("SELECT count(*) FROM batches WHERE status='accepted'")==3)})
            with source.open('ab') as f:f.write(line(0)+b'{invalid\n'+b'{"event_type":"flow"}\n')
            phases.append({'phase':'duplicate_invalid_unsupported_audit','seconds':wait_until(lambda:checkpoint_query("SELECT count(*) FROM batches WHERE status='accepted'")==4)})
            assert events()==9
            # A real server outage, then rename/create rotation while the agent remains running.
            instance.stop()
            def rotate():
                try:source.rename(source.with_name('eve.json.1'));return True
                except PermissionError:return False  # Windows may be in a bounded read; wait for its handle to close.
            wait_until(rotate,5)
            source.write_bytes(b''.join(line(n) for n in range(9,12)))
            phases.append({'phase':'real_connection_failure','seconds':wait_until(lambda:checkpoint_query("SELECT count(*) FROM audit WHERE code='network_error'")>0)})
            assert checkpoint_query("SELECT count(*) FROM batches WHERE status='pending'")==1
            instance.start()
            phases.append({'phase':'recovery_and_rotated_three','seconds':wait_until(lambda:events()==12 and checkpoint_query("SELECT count(*) FROM batches WHERE status='accepted'")==5)})
            stop_agent()
            with sqlite3.connect(checkpoint) as db:
                db.row_factory=sqlite3.Row
                rows=[dict(r) for r in db.execute('SELECT seq,id,source_id,start,end,start_line,end_line,sha256,records,status,attempts,report FROM batches ORDER BY seq')]
                audit=[dict(r) for r in db.execute('SELECT seq,code,batch_id,details FROM audit ORDER BY seq')]
                quarantined=db.execute('SELECT count(*) FROM batches WHERE body IS NOT NULL').fetchone()[0]
                offsets=[dict(r) for r in db.execute('SELECT id,offset,line,current FROM sources ORDER BY rowid')]
            assert len(rows)==5 and quarantined==1 and sum(r['records'] for r in rows)==15
            assert sum(json.loads(r['report'])['discarded'] for r in rows)==2
            assert sum(json.loads(r['report'])['duplicates'] for r in rows)==1
            # Repeat with the same sensor through the real API: original fingerprints remain compatible.
            service_token=client.post('/api/auth/login',json={'username':'iter11-isolated-service','password':service_password}).json()['access_token']
            repeated=client.post('/api/events/import/eve?sensor_id=iter11-live&filename=synthetic-repeat.jsonl',
                content=b''.join(line(n) for n in range(12)),headers={'Authorization':'Bearer '+service_token,'Content-Type':'application/x-ndjson'})
            assert repeated.status_code==200 and repeated.json()['imported']==0 and repeated.json()['duplicates']==12
            with engine.connect() as db:
                count=db.scalar(text('SELECT count(*) FROM events'))
                evidence=db.scalar(text('SELECT count(*) FROM event_evidence'))
                authors=db.execute(text('SELECT DISTINCT author_id FROM event_evidence')).scalars().all()
                head=db.scalar(text('SELECT version_num FROM alembic_version'))
                incidents=db.scalar(text('SELECT count(*) FROM incidents'))
            assert (count,evidence,head)==(12,25,'0009') and authors==[uid]
            logs=(instance.directory/'agent.log').read_text(encoding='utf-8')
            assert service_password not in logs and password not in logs and token not in logs and service_token not in logs
            assert not re.search(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|ITER11 SYNTHETIC FILE REPLAY',logs)
            result={'generated_at':datetime.now(timezone.utc).isoformat(),'data_kind':'synthetic EVE file replay, no traffic capture',
                    'dialect':dialect,'transport':'real TCP loopback, independent Uvicorn and agent processes',
                    'python':platform.python_version(),'os':platform.platform(),'seed':202611,'poll_seconds':.1,'batch_lines':3,
                    'events':count,'evidence_appearances':evidence,'incidents':incidents,'migration':head,
                    'phases':phases,'batches':rows,'audit':audit,'offsets':offsets,'quarantined_batches':quarantined,
                    'duplicate_repeat':repeated.json(),'logs_checked_no_credentials_or_event_bodies':True,'second_reader_rejected':True,
                    'source_sha256':hashlib.sha256(b''.join(line(n) for n in range(12))).hexdigest(),
                    'agent_source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'agent').rglob('*.py')},
                    'total_seconds':time.perf_counter()-started}
            with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
            with output.with_suffix('.csv').open('x',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['seq','id','start','end','start_line','end_line','records','attempts','imported','duplicates','discarded'])
                for row in rows:
                    report=json.loads(row['report']);writer.writerow([*[row[k] for k in ('seq','id','start','end','start_line','end_line','records','attempts')],*[report[k] for k in ('imported','duplicates','discarded')]])
            print(json.dumps({'evidence':str(output.relative_to(ROOT)),'events':count,'appearances':evidence,'batches':len(rows),'passed':True}))
        finally:
            stop_agent();engine.dispose()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',choices=['sqlite','postgresql'],default='sqlite');parser.add_argument('--label',default='final')
    parser.add_argument('--iteration',choices=['11','14'],default='11');args=parser.parse_args()
    if not re.fullmatch('[a-zA-Z0-9_-]{1,30}',args.label):parser.error('Invalid label')
    run(args.database,args.label,args.iteration)
