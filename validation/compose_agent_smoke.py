"""Optional-profile validation on NEW Compose volumes, Linux agent, no host source mounts."""
import json
import os
import re
import secrets
import subprocess
import time
from datetime import datetime, timezone
from uuid import uuid4
import httpx
from .isolated import ROOT


def main():
    project='smartir-iter11-'+uuid4().hex[:8]
    directory=ROOT/'.test-runs'/project;directory.mkdir(parents=True,exist_ok=False)
    password=secrets.token_urlsafe(24)
    env={**os.environ,'DB_PASSWORD':secrets.token_urlsafe(32),'JWT_SECRET':secrets.token_urlsafe(48),
         'ITER11_SERVICE_PASSWORD':password}
    override=directory/'override.yaml'
    override.write_text('''services:
  api:
    ports: !override ["127.0.0.1:58011:8000"]
  web:
    ports: !override ["127.0.0.1:55181:5173"]
  eve-agent:
    env_file: !reset []
    environment:
      SMARTIR_AGENT_USERNAME: iter11-compose-service
      SMARTIR_AGENT_PASSWORD: ${ITER11_SERVICE_PASSWORD}
      SMARTIR_AGENT_PASSWORD_FILE: ""
      SMARTIR_AGENT_SENSOR: iter11-compose
''',encoding='utf-8')
    base=['docker','compose','-p',project,'-f','compose.yaml','-f','compose.agent.yaml','-f',str(override)]
    command=base+['--profile','eve-agent']
    started=False
    def execute(args,input=None):
        result=subprocess.run(args,cwd=ROOT,env=env,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:raise RuntimeError('Isolated Docker command failed; diagnostics withheld to prevent exposing environment')
        return result.stdout.decode('utf-8').strip()
    def compose(*args,input=None):return execute(command+list(args),input)
    def count(table):
        return int(compose('exec','-T','db','psql','-U','smartir','-d','smartir','-Atc',f'SELECT count(*) FROM {table}'))
    def wait(predicate):
        start=time.monotonic()
        while time.monotonic()-start<45:
            if predicate():return
            time.sleep(.25)
        raise RuntimeError('Isolated Compose assertion timed out')
    try:
        default=execute(base+['config','--services']).splitlines()
        assert set(default)=={'api','db','web'}
        compose('config','--quiet')
        started=True
        compose('up','--build','-d')
        with httpx.Client(trust_env=False,timeout=2) as client:
            def healthy():
                try:return client.get('http://127.0.0.1:58011/health').status_code==200
                except httpx.HTTPError:return False
            wait(healthy)
            assert client.get('http://127.0.0.1:55181/').status_code==200
        seed="""import sys,json
from app.database import Session
from app.models import User
from app.security import password_hasher
try:
 with Session.begin() as db:db.add(User(username='iter11-compose-service',password_hash=password_hasher.hash(json.load(sys.stdin)['password']),role='analista',eve_only=True))
except Exception:raise SystemExit('isolated fixture setup failed') from None
"""
        compose('exec','-T','api','python','-c',seed,input=json.dumps({'password':password}).encode())
        # Ephemeral writer accesses only this newly-created named test volume. No user's filesystem mounted.
        image=project+'-eve-agent'
        writer=['docker','run','--rm','-i','--label','smartir.validation=iter11','--user','0',
                '-v',project+'_agent_input:/input','--entrypoint','python',image,'-c']
        from sys import path
        path.insert(0,str(ROOT/'agent'))
        from smartir_agent.synthetic import line
        execute(writer+["import sys;from pathlib import Path;Path('/input/eve.json').write_bytes(sys.stdin.buffer.read())"],b''.join(line(n) for n in range(6)))
        wait(lambda:count('events')==6)
        compose('restart','eve-agent')
        time.sleep(2)
        assert count('events')==count('event_evidence')==6
        execute(writer+["import sys;from pathlib import Path;p=Path('/input/eve.json');p.rename('/input/eve.json.1');p.write_bytes(sys.stdin.buffer.read())"],b''.join(line(n) for n in range(6,12)))
        wait(lambda:count('events')==12)
        execute(writer+["import sys;from pathlib import Path\nwith Path('/input/eve.json').open('ab') as f:f.write(sys.stdin.buffer.read())"],line(0)+b'{invalid\n')
        wait(lambda:count('event_evidence')==13)
        assert count('events')==12
        checkpoint=compose('exec','-T','eve-agent','python','-c',"import sqlite3,json;d=sqlite3.connect('/state/state.db');print(json.dumps({'accepted':d.execute(\"SELECT count(*) FROM batches WHERE status='accepted'\").fetchone()[0],'quarantined':d.execute('SELECT count(*) FROM batches WHERE body IS NOT NULL').fetchone()[0],'sources':d.execute('SELECT count(*) FROM sources').fetchone()[0]}))")
        wait(lambda:json.loads(compose('exec','-T','eve-agent','python','-c',"import sqlite3,json;d=sqlite3.connect('/state/state.db');print(json.dumps(d.execute(\"SELECT count(*) FROM batches WHERE status='accepted'\").fetchone()[0]))"))==3)
        checkpoint=compose('exec','-T','eve-agent','python','-c',"import sqlite3,json;d=sqlite3.connect('/state/state.db');print(json.dumps({'accepted':d.execute(\"SELECT count(*) FROM batches WHERE status='accepted'\").fetchone()[0],'quarantined':d.execute('SELECT count(*) FROM batches WHERE body IS NOT NULL').fetchone()[0],'sources':d.execute('SELECT count(*) FROM sources').fetchone()[0]}))")
        assert json.loads(checkpoint)=={'accepted':3,'quarantined':1,'sources':2}
        logs=compose('logs','--no-color','eve-agent')
        assert password not in logs and not re.search(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|ITER11 SYNTHETIC FILE REPLAY',logs)
        version=compose('exec','-T','api','python','-m','alembic','current')
        assert '0009' in version
        runtime=json.loads(compose('exec','-T','eve-agent','python','-c',"import os,platform,json;print(json.dumps({'system':platform.system(),'uid':os.getuid(),'python':platform.python_version()}))"))
        assert runtime['uid']==10001 and runtime['system']=='Linux'
        result={'generated_at':datetime.now(timezone.utc).isoformat(),'project':project,'data_kind':'synthetic EVE file only; no capture',
                'default_services':default,'profile':'eve-agent','agent_runtime':runtime,
                'host_source_mounts':False,'health_http':200,'web_http':200,'migration':'0009',
                'postgresql':compose('exec','-T','db','psql','-U','smartir','-d','smartir','-Atc','SHOW server_version'),
                'events':12,'event_evidence':13,'checkpoint':json.loads(checkpoint),'restart_without_replay':True,
                'rename_create_rotation':True,'original_services_modified':False,'volumes_removed':False,
                'logs_checked_no_credentials_or_bodies':True}
        output=ROOT/'docs/resultados'/f'iter11_compose_{project}.json'
        with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({'evidence':str(output.relative_to(ROOT)),'passed':True}))
    finally:
        if started:compose('stop')  # Keep every named volume; never down -v or prune.


if __name__=='__main__':main()
