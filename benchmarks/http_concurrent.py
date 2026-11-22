"""Real localhost HTTP only, fresh dedicated test schemas; no arbitrary target option."""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from validation.isolated import Isolated, ROOT
from benchmarks.synthetic_events import batches


def percentile(values, p):
    if not values: return None
    values=sorted(values);position=(len(values)-1)*p;lower=int(position)
    return values[lower]+(values[min(lower+1,len(values)-1)]-values[lower])*(position-lower)


def latencies(values):
    return {name:percentile(values,p) for name,p in [('p50',.5),('p95',.95),('p99',.99)]}


async def measure(api, mode, clients, protocol, headers, payloads):
    semaphore=asyncio.Semaphore(clients)
    async with httpx.AsyncClient(base_url=api.base_url,trust_env=False,timeout=protocol['request_timeout_seconds'],
                                limits=httpx.Limits(max_connections=clients,max_keepalive_connections=clients)) as client:
        async def request(i):
            async with semaphore:
                start=time.perf_counter()
                try:
                    if mode=='ingestion':
                        response=await client.post('/api/events/import/eve?filename=iter10-synthetic.eve.jsonl&sensor_id=iter10-load',
                            content=payloads[i],headers={**headers,'Content-Type':'application/x-ndjson'})
                    else:
                        response=await client.get('/api/analytics/dashboard',headers=headers,params={
                            'start':'2026-01-01T00:00:00Z','end':'2026-01-02T00:00:00Z','time_basis':'event_timestamp'})
                    elapsed=time.perf_counter()-start
                    data=response.json() if response.status_code==200 else {}
                    return {'sample':i,'status':response.status_code,'seconds':elapsed,
                            'retry_after':response.headers.get('Retry-After'),
                            'imported':data.get('imported',0),'duplicates':data.get('duplicates',0),
                            'dashboard_events':data.get('totals',{}).get('events')}
                except httpx.HTTPError as exc:
                    return {'sample':i,'status':0,'seconds':time.perf_counter()-start,'error':type(exc).__name__,
                            'imported':0,'duplicates':0,'retry_after':None}
        start=time.perf_counter()
        samples=await asyncio.gather(*(request(i) for i in range(protocol['requests_per_scenario'])))
        return samples,time.perf_counter()-start


def scenario(mode, clients, protocol):
    api=Isolated('postgresql')
    with api.running():
        with httpx.Client(base_url=api.base_url,trust_env=False,timeout=30) as client:
            username,password=api.credentials['administrador']
            token=client.post('/api/auth/login',json={'username':username,'password':password}).json()['access_token']
            headers={'Authorization':'Bearer '+token}
            fixture=next(batches(1000,seed=protocol['seed']))
            response=client.post('/api/events/import/eve?filename=fixture-synthetic.jsonl&sensor_id=iter10-fixture',
                headers={**headers,'Content-Type':'application/x-ndjson'},content=fixture)
            assert response.status_code==200 and response.json()['imported']==1000
            baseline=api.snapshot()
            from sqlalchemy import create_engine,text
            engine=create_engine(api.url)
            def fixture_hash():
                with engine.connect() as db:
                    rows=db.execute(text("SELECT fingerprint,raw_event,incident_id FROM events WHERE source='suricata:iter10-fixture' ORDER BY fingerprint")).all()
                    return len(rows),hashlib.sha256(json.dumps([list(r) for r in rows]).encode()).hexdigest()
            fixture_before=fixture_hash()
            api.stop();api.start()  # Fresh process/default counters for each independent measured scenario.
            payloads=list(batches(10000,seed=protocol['seed']+1,batch_size=protocol['events_per_request']))[:protocol['requests_per_scenario']]
            every=protocol['duplicate_request_every']
            for i in range(every-1,len(payloads),every):payloads[i]=payloads[i-every+1]
            samples,duration=asyncio.run(measure(api,mode,clients,protocol,headers,payloads))
            success=[s for s in samples if s['status']==200];limited=[s for s in samples if s['status']==429]
            unavailable=[s for s in samples if s['status']==503]
            errors=[s for s in samples if s['status'] not in (200,429,503)]
            after=api.snapshot()
            imported=sum(s['imported'] for s in success)
            accepted_unique=set()
            for s in success:
                if mode=='ingestion': accepted_unique.update(payloads[s['sample']].splitlines())
            correct=after['events']['rows']==1000+len(accepted_unique) and imported==len(accepted_unique)
            if mode=='dashboard':correct=after==baseline and all(s['dashboard_events']==1000 for s in success)
            # Read-only verification of fixture fingerprints on its own isolated schema.
            fixture_after=fixture_hash()
            engine.dispose()
            baseline_preserved=fixture_before==fixture_after and fixture_after[0]==1000 and after['users']==baseline['users']
            retry_ok=all(str(s['retry_after']).isdigit() and int(s['retry_after'])>0 for s in limited)
            criteria={'unexpected_errors_zero':not errors,'http_503_zero':not unavailable,'has_success':bool(success),
                      '429_retry_after_valid':retry_ok,'exact_event_counts':correct,'baseline_preserved':baseline_preserved,
                      'success_p95_within_5s':bool(success) and percentile([s['seconds'] for s in success],.95)<=5}
            return {'mode':mode,'clients':clients,'requests':len(samples),'success':len(success),'http_429':len(limited),
                    'http_503':len(unavailable),'unexpected_errors':len(errors),'duration_seconds':duration,
                    'requests_per_second':len(samples)/duration,'imported_events':imported,
                    'events_per_second':imported/duration if mode=='ingestion' else None,
                    'duplicates':sum(s['duplicates'] for s in success),'stored_events':after['events']['rows'],
                    'latencies_seconds':{key:latencies([s['seconds'] for s in values]) for key,values in
                        [('all',samples),('success',success),('429',limited),('503',unavailable)]},
                    'criteria':criteria,'accepted':all(criteria.values()),'samples':samples}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='final');args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Alphanumeric label only')
    target=ROOT/'docs/resultados'/f'iter10_http_concurrent_{args.label}.json'
    if target.exists():parser.error('Historical evidence exists: choose another label')
    protocol_path=ROOT/'benchmarks/protocol_iter10.json'
    protocol=json.loads(protocol_path.read_text(encoding='utf-8'))
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'protocol':protocol,
            'protocol_sha256':hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'environment':{'os':platform.platform(),'python':platform.python_version(),'logical_cpus':os.cpu_count(),
                           'processor':platform.processor(),'transport':'TCP loopback','database':'PostgreSQL16 temporary port55440',
                           'resources':'CPU/RSS not sampled by this HTTP runner; no estimates'},'scenarios':[]}
    for mode in protocol['scenarios']:
        for clients in protocol['clients']:
            record=scenario(mode,clients,protocol);result['scenarios'].append(record)
            print(json.dumps({k:record[k] for k in ('mode','clients','success','http_429','http_503','unexpected_errors','accepted')}),flush=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with target.with_suffix('.csv').open('w',encoding='utf-8',newline='') as out:
        writer=csv.writer(out);writer.writerow(['mode','clients','sample','status','seconds','retry_after','imported','duplicates'])
        for record in result['scenarios']:
            for sample in record['samples']:writer.writerow([record['mode'],record['clients'],*[sample.get(k) for k in ('sample','status','seconds','retry_after','imported','duplicates')]])


if __name__=='__main__':main()
