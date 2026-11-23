"""Real Chromium + loopback API, fresh schema/file only. No operational credentials or data."""
import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
import httpx
from .isolated import ROOT, Isolated, port
from .journey import journey


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--database',choices=['sqlite','postgresql'],default='sqlite')
    parser.add_argument('--label',default='final');parser.add_argument('--iteration',choices=['13','14'],default='13');args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Invalid label')
    target=ROOT/'docs/resultados'/f'iter{args.iteration}_frontend_{args.database}_{args.label}.json'
    if target.exists():raise RuntimeError('Evidence exists; choose a new label')
    instance=Isolated(args.database)
    with instance.running(),httpx.Client(base_url=instance.base_url,trust_env=False,timeout=120) as client:
        result=journey(client,instance.credentials)
        username,password=instance.credentials['administrador']
        token=client.post('/api/auth/login',json={'username':username,'password':password}).json()['access_token']
        h={'Authorization':'Bearer '+token}
        identity=client.get('/api/auth/me',headers=h).json()
        lines=[{'timestamp':f'2026-01-02T00:01:0{i}.123456Z','event_type':'alert','src_ip':'192.0.2.10','dest_ip':'198.51.100.20',
            'proto':'ICMP','alert':{'signature':'SMARTIR WSL2 LAB ICMP TEST','signature_id':9900013,'category':'','severity':3},'synthetic':True} for i in range(4)]
        r=client.post('/api/events/import/eve?sensor_id=iter13-synthetic&filename=synthetic13.jsonl',headers={**h,'Content-Type':'application/x-ndjson'},
            content='\n'.join(json.dumps(s) for s in lines)+'\n')
        assert r.status_code==200 and r.json()['imported']==4
        incident=next(i for i in client.get('/api/incidents',headers=h).json() if i['event_type']=='prueba_icmp')
        web_port=port();prefix=instance.directory/'frontend-evidence'
        environment={**instance.environment,'VITE_API_URL':'','VALIDATION_API_TARGET':instance.base_url,
            'VALIDATION_WEB_PORT':str(web_port),'VALIDATION_CREDENTIALS':json.dumps(instance.credentials),
            'VALIDATION_IDS':json.dumps({'admin':identity['id'],'lab_incident':incident['id'],'ml_run':result['ml_run_id']}),
            'VALIDATION_JWT_SECRET':instance.environment['JWT_SECRET'],'VALIDATION_OUTPUT':str(prefix)}
        run=subprocess.run(['node','node_modules/@playwright/test/cli.js','test','--config','tests/frontend13.config.ts'],
            cwd=ROOT/'frontend',env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=480)
        (instance.directory/'frontend.log').write_bytes(run.stdout)
        print('Browser exit:',run.returncode,'; private diagnostics:',instance.directory.name,flush=True)
        if run.returncode:raise RuntimeError('Browser validation failed; private log retained, not published')
        browser=json.loads(prefix.with_suffix('.browser.json').read_text(encoding='utf-8'))
        for source in instance.directory.glob('frontend-evidence.*'):
            destination=target.with_name(target.stem+source.name.removeprefix('frontend-evidence'))
            if destination.exists():raise RuntimeError('Evidence exists')
            shutil.copyfile(source,destination)
        result={'generated_at':datetime.now(timezone.utc).isoformat(),'database':args.database,'transport':'real HTTP TCP loopback, Chromium and API processes',
            'journey_checks':result['checks'],'browser':browser,'data_kind':'synthetic isolated fixtures; NOT live traffic',
            'user_database_read_or_written':False,'migration_head':'0009','credentials_saved':False}
        with target.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps({'evidence':str(target.relative_to(ROOT)),'passed':True}))


if __name__=='__main__':main()
