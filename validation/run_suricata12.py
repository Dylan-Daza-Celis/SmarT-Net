"""Engine-generated SYNTHETIC offline EVE -> existing Windows agent -> isolated API/DB."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import re
from datetime import datetime, timezone
import httpx
from .isolated import Isolated, ROOT, port
from .synthetic_icmp import make_pcap


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--database',choices=['sqlite','postgresql'],default='sqlite');parser.add_argument('--label',default='final')
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--iteration',choices=['12','13','14'],default='12')
    args=parser.parse_args()
    if not re.fullmatch('[a-zA-Z0-9_-]{1,30}',args.label):parser.error('Invalid label')
    directory=args.source_dir.resolve()
    if not directory.is_relative_to((ROOT/'.test-runs').resolve()):parser.error('Only isolated generated source under .test-runs')
    source=directory/'engine-synthetic-alerts.eve.jsonl'
    provenance=json.loads((directory/'suricata-validation.json').read_text(encoding='utf-8'))
    body=source.read_bytes();original=[json.loads(s) for s in body.splitlines()]
    assert provenance['live_interface_opened'] is False and provenance['synthetic_packets']==4
    assert provenance['source_pcap_sha256']==hashlib.sha256(make_pcap()).hexdigest()
    assert provenance['source_alerts_sha256']==hashlib.sha256(body).hexdigest()
    assert len(original)==4 and all(r['src_ip']=='192.0.2.10' and r['dest_ip']=='198.51.100.20' and r['alert']['signature_id']==9900012 for r in original)
    target=ROOT/'docs/resultados'/f'iter{args.iteration}_pipeline_{args.database}_{args.label}.json'
    if target.exists():parser.error('Evidence exists; choose another label')
    instance=Isolated(args.database);start=time.perf_counter()
    with instance.running(),httpx.Client(base_url=instance.base_url,trust_env=False,timeout=30) as client:
        admin,password=instance.credentials['administrador']
        token=client.post('/api/auth/login',json={'username':admin,'password':password}).json()['access_token']
        headers={'Authorization':'Bearer '+token};secret=secrets.token_urlsafe(24)
        user=client.post('/api/users',headers=headers,json={'username':'iter12-service','password':secret,'role':'analista','eve_only':True})
        assert user.status_code==201
        state=instance.directory/'agent-state'
        env={**instance.environment,'PYTHONPATH':str(ROOT/'agent'),'SMARTIR_AGENT_USERNAME':'iter12-service',
             'SMARTIR_AGENT_PASSWORD':secret,'SMARTIR_AGENT_PASSWORD_FILE':''}
        command=[sys.executable,'-m','smartir_agent','--file',str(source),'--state-dir',str(state),
                 '--api-url',instance.base_url,'--sensor','iter12-engine-synthetic','--once']
        runs=[]
        for _ in range(2):
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
            assert result.returncode==0 and secret.encode() not in result.stdout and b'eyJ' not in result.stdout
            runs.extend(json.loads(s) for s in result.stdout.decode().splitlines())
        with sqlite3.connect(state/'state.db') as db:
            offset=db.execute('SELECT offset FROM sources WHERE current=1').fetchone()[0]
            accepted=db.execute("SELECT count(*) FROM batches WHERE status='accepted'").fetchone()[0]
            receipt=json.loads(db.execute('SELECT report FROM batches ORDER BY seq DESC LIMIT 1').fetchone()[0])
        assert offset==len(body) and accepted==1 and receipt['imported']==4 and receipt['unknown']==0
        service_token=client.post('/api/auth/login',json={'username':'iter12-service','password':secret}).json()['access_token']
        repeated=client.post('/api/events/import/eve?sensor_id=iter12-engine-synthetic&filename=synthetic-repeat.jsonl',
            headers={'Authorization':'Bearer '+service_token,'Content-Type':'application/x-ndjson'},content=body)
        assert repeated.status_code==200 and repeated.json()['duplicates']==4 and repeated.json()['imported']==0
        incidents=client.get('/api/incidents',headers=headers).json()
        assert len(incidents)==1 and incidents[0]['event_type']=='prueba_icmp' and incidents[0]['event_count']==4
        incident=incidents[0];detail=client.get('/api/incidents/'+incident['id'],headers=headers).json()
        records=[]
        for event in detail['events']:
            data=client.get('/api/events/'+event['id'],headers=headers).json()
            m=data['adapter_metadata'];evidence=client.get('/api/events/'+event['id']+'/evidence',headers=headers).json()
            assert m['suricata_severity']==3 and m['alert_criticality']['value']==40 and m['alert_criticality']['observed'] is False
            assert data['asset_criticality']==50 and data['asset_criticality_observed'] is False and len(evidence)==2
            assert json.loads(data['raw_event']) in original and data['event_type']=='prueba_icmp'
            records.append({k:data[k] for k in ('id','event_type','event_timestamp','severity','asset_criticality','asset_criticality_observed','fingerprint','adapter_metadata')})
        evaluations=client.get('/api/incidents/'+incident['id']+'/evaluations',headers=headers).json()
        assert len(evaluations)==1 and incident['score']==50 and incident['priority']=='Alta'
        result={'generated_at':datetime.now(timezone.utc).isoformat(),'database':args.database,
            'provenance':provenance,'live_capture':False,'agent':'unmodified iteration11 process with restart on same checkpoint',
            'agent_runs':runs,'checkpoint_offset':offset,'checkpoint_batches':accepted,'receipt':receipt,
            'repeat_import':repeated.json(),'incidents':1,'incident':{k:incident[k] for k in ('id','event_type','score','priority','event_count')},
            'events':records,'evaluations':evaluations,'duration_seconds':time.perf_counter()-start,
            'interpretation':'Generic weighted-v2 score for a declared test, NOT observed attack risk or MTTD/MTTR'}
        if args.browser:
            import shutil
            web_port=port();prefix=instance.directory/'browser-evidence'
            browser_env={**instance.environment,'VITE_API_URL':'','VALIDATION_API_TARGET':instance.base_url,
                'VALIDATION_WEB_PORT':str(web_port),'VALIDATION_CREDENTIALS':json.dumps(instance.credentials),
                'VALIDATION_OUTPUT':str(prefix)}
            browser=subprocess.run(['node','node_modules/@playwright/test/cli.js','test','--config','tests/suricata12.config.ts'],
                cwd=ROOT/'frontend',env=browser_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (instance.directory/'browser.log').write_bytes(browser.stdout)
            if browser.returncode:raise RuntimeError('Browser validation failed; isolated private diagnostics retained')
            result['browser']=json.loads(prefix.with_suffix('.browser.json').read_text(encoding='utf-8'))
            for file in instance.directory.glob('browser-evidence.*'):
                destination=target.with_name(target.stem+file.name.removeprefix('browser-evidence'))
                if destination.exists():raise RuntimeError('Evidence exists')
                shutil.copyfile(file,destination)
        with target.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        with target.with_suffix('.csv').open('x',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['id','event_type','suricata_priority','alert_index','alert_level','asset_criticality','asset_observed'])
            for row in records:writer.writerow([row['id'],row['event_type'],3,40,'Media',50,False])
        print(json.dumps({'evidence':str(target.relative_to(ROOT)),'passed':True,'events':4,'incidents':1,'duplicate_replay':4}))


if __name__=='__main__':main()
