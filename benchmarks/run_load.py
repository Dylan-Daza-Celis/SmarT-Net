"""Isolated synthetic ASGI benchmark. No cleanup, no arbitrary HTTP target or DB URL."""
import argparse
import csv
import ctypes
import json
import hashlib
import io
import math
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import tarfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
sys.path.insert(0, str(ROOT/'benchmarks'))
from synthetic_events import batches, fingerprint


def resources():
    result = {'cpu_process_seconds': time.process_time(), 'rss_bytes': None, 'peak_rss_bytes': None}
    if os.name == 'nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)]+[(n, ctypes.c_size_t) for n in (
                'peak', 'working', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        api = ctypes.windll.psapi.GetProcessMemoryInfo
        api.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]; api.restype = wintypes.BOOL
        if api(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
            result.update(rss_bytes=int(counters.working), peak_rss_bytes=int(counters.peak))
    else:
        try:
            import resource
            raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            result['peak_rss_bytes'] = int(raw*(1 if sys.platform == 'darwin' else 1024))
        except (ImportError, OSError): pass
    return result


def percentiles(samples):
    if not samples: return {'n': 0, 'total_seconds': None, 'p50': None, 'p95': None, 'p99': None}
    data = sorted(samples)
    def p(fraction):
        k = (len(data)-1)*fraction; low = math.floor(k); high = math.ceil(k)
        return data[low]+(data[high]-data[low])*(k-low)
    return {'n':len(data), 'total_seconds':sum(data), 'p50':p(.5), 'p95':p(.95), 'p99':p(.99)}


def hardware():
    info={'cpu_model':platform.processor(),'logical_cpus':os.cpu_count(),'total_ram_bytes':None}
    if os.name=='nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                info['cpu_model']=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in (
                    'total','available','total_page','available_page','total_virtual','available_virtual','extended')]
            memory=Memory();memory.length=ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):info['total_ram_bytes']=int(memory.total)
        except OSError:pass
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', required=True, choices=['baseline', 'optimized', 'hardened'])
    parser.add_argument('--sizes', type=int, nargs='+', default=[100,1000,10000], choices=[100,1000,10000])
    parser.add_argument('--postgres-isolated', action='store_true', help='Only localhost:55438/smartir_test; retains a fresh UUID schema')
    parser.add_argument('--baseline-ref', help='Hex commit to archive/read for baseline only; no checkout or tracked-file changes')
    parser.add_argument('--run-label',default='',help='Separate output label; existing results are never overwritten')
    args = parser.parse_args()
    if len(args.sizes)!=len(set(args.sizes)):parser.error('Duplicate scenario sizes are not allowed')
    import re
    if args.run_label and not re.fullmatch('[a-z0-9_-]{1,30}',args.run_label): parser.error('Invalid run-label')
    output=ROOT/'docs/resultados'/f'iter09_{args.phase}_{"pg" if args.postgres_isolated else "sqlite"}{"_"+args.run_label if args.run_label else ""}'
    if output.with_suffix('.json').exists() or output.with_suffix('.csv').exists(): parser.error('Results already exist; use a new --run-label')
    protocol = json.loads((ROOT/'benchmarks/protocol_iter09.json').read_text())
    workspace = ROOT/'.test-runs'/('iter09-'+args.phase+'-'+uuid4().hex)
    workspace.mkdir(parents=True, exist_ok=False)
    backend=ROOT/'backend';source_ref=None
    if args.baseline_ref:
        if args.phase!='baseline' or not re.fullmatch('[a-fA-F0-9]{7,40}',args.baseline_ref): parser.error('Use a hex commit for baseline only')
        source_ref=subprocess.check_output(['git','rev-parse','--verify',args.baseline_ref],cwd=ROOT,text=True).strip()
        archive=subprocess.check_output(['git','archive',source_ref,'backend'],cwd=ROOT)
        destination=workspace/'baseline-source';destination.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            for member in package.getmembers():
                target=(destination/member.name).resolve()
                if not target.is_relative_to(destination.resolve()): raise ValueError('Unsafe archive path')
                if member.isdir(): target.mkdir(parents=True,exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(package.extractfile(member).read())
                else: raise ValueError('Links not accepted in baseline archive')
        backend=destination/'backend';sys.path.insert(0,str(backend))
    source_hash=hashlib.sha256()
    for path in sorted(backend.rglob('*.py')):
        source_hash.update(path.relative_to(backend).as_posix().encode());source_hash.update(path.read_bytes())
    # Override BEFORE importing the application: never reads the user's normal DATABASE_URL/JWT_SECRET.
    os.environ['DATABASE_URL'] = 'sqlite://'
    os.environ['JWT_SECRET'] = secrets.token_urlsafe(48)
    os.environ['CORRELATION_WINDOW_SECONDS']=str(protocol['correlation_window_seconds'])
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event, select, func
    from sqlalchemy.orm import sessionmaker
    from alembic import command
    from alembic.config import Config
    from app import database, security, main as application
    from app.models import User, Event, Incident, RiskEvaluation, EventEvidence
    from app.lifecycle import utc
    import fastapi, sqlalchemy
    results = {'protocol':protocol, 'phase':args.phase, 'status':'running',
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_ref':source_ref,'backend_source_sha256':source_hash.hexdigest(),
        'environment':{'platform':platform.platform(), 'machine':platform.machine(), 'processor':platform.processor(),
            'logical_cpus':os.cpu_count(), 'python':sys.version.split()[0], 'fastapi':fastapi.__version__,
            'sqlalchemy':sqlalchemy.__version__, 'database':'postgresql-isolated-55438' if args.postgres_isolated else 'sqlite-isolated',
            'resource_scope':'client+ASGI app in this Python process; PostgreSQL server resources not measured',
            'http_network_included':False,'postgres_loopback_io_included':args.postgres_isolated,
            'correlation_window_seconds':protocol['correlation_window_seconds']}, 'scenarios':[]}
    results['environment']['hardware']=hardware()
    for size in args.sizes:
        url = 'postgresql+psycopg://postgres@localhost:55438/smartir_test' if args.postgres_isolated else 'sqlite:///'+str(workspace/f'{size}.db')
        engine = create_engine(url, connect_args={'check_same_thread':False} if not args.postgres_isolated else {})
        schema = 'bench_'+uuid4().hex
        if args.postgres_isolated:
            with engine.begin() as connection: connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            @event.listens_for(engine, 'connect')
            def search_path(connection, record):
                with connection.cursor() as cursor: cursor.execute(f'SET search_path TO "{schema}"')
                connection.commit()
            engine.dispose()
        else:
            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, record): connection.execute('PRAGMA foreign_keys=ON')
        session = sessionmaker(bind=engine)
        for module in (database, security, application): module.Session = session
        database.engine = engine
        with engine.connect() as connection:
            results['environment']['database_version']=connection.exec_driver_sql('SELECT version()' if args.postgres_isolated else 'SELECT sqlite_version()').scalar_one()
        command.upgrade(Config(str(backend/'alembic.ini')), 'head')
        with session.begin() as db:
            user=User(username='synthetic-benchmark-only',role='administrador',password_hash=security.password_hasher.hash(secrets.token_urlsafe(32)))
            db.add(user);db.flush();token=security.issue_token(user)
        if hasattr(application.app.state, 'abuse'): application.app.state.abuse.reset()
        sql = {}; current = ['setup']
        @event.listens_for(engine, 'before_cursor_execute')
        def before(connection, cursor, statement, parameters, context, many): context._bench_start=time.perf_counter()
        @event.listens_for(engine, 'after_cursor_execute')
        def after(connection, cursor, statement, parameters, context, many):
            row=sql.setdefault(current[0], {'statements':0,'seconds':0.0})
            row['statements']+=1;row['seconds']+=time.perf_counter()-context._bench_start
        samples={};errors=[]
        with TestClient(application.app, base_url='http://localhost', raise_server_exceptions=False) as client:
            h={'Authorization':'Bearer '+token}
            def call(label, method, path, expected=200, **kwargs):
                current[0]=label;start=time.perf_counter()
                response=client.request(method,path,headers={**h,**kwargs.pop('headers',{})},**kwargs)
                samples.setdefault(label,[]).append(time.perf_counter()-start)
                if response.status_code!=expected: errors.append({'operation':label,'status':response.status_code})
                return response
            start_resource=resources();start=time.perf_counter(); imported=duplicates=0
            for block in batches(size, protocol['seed']):
                response=call('import','POST','/api/events/import/eve?filename=synthetic.jsonl&sensor_id=bench-'+str(size),
                    content=block,headers={'Content-Type':'application/x-ndjson'})
                if response.status_code==200: imported+=response.json()['imported']
            fresh_seconds=time.perf_counter()-start
            for block in batches(size, protocol['seed']):
                response=call('duplicate_import','POST','/api/events/import/eve?filename=synthetic.jsonl&sensor_id=bench-'+str(size),
                    content=block,headers={'Content-Type':'application/x-ndjson'})
                if response.status_code==200: duplicates+=response.json()['duplicates']
            query={'start':'2026-01-01T00:00:00Z','end':'2026-01-03T00:00:00Z','time_basis':'event_timestamp'}
            for _ in range(protocol['dashboard_samples']): call('dashboard','GET','/api/analytics/dashboard',params=query)
            for _ in range(protocol['report_creation_samples']):
                response=call('report_creation','POST','/api/analytics/reports',expected=201,json=query)
                if response.status_code==201:
                    for format in ('json','csv','pdf'):
                        call('export_'+format,'GET','/api/analytics/reports/'+response.json()['id'],params={'format':format})
            end_resource=resources()
        with session() as db:
            persisted=db.scalar(select(func.count()).select_from(Event))
            incidents=db.scalar(select(func.count()).select_from(Incident))
            kinds=db.scalar(select(func.count(func.distinct(Incident.event_type))))
            semantic=hashlib.sha256()
            for key,window,score,priority,explanation in db.execute(select(Incident.correlation_key,Incident.window_start,
                Incident.score,Incident.priority,Incident.explanation).order_by(Incident.correlation_key,Incident.window_start)):
                semantic.update(json.dumps([key,utc(window).isoformat(),score,priority,json.loads(explanation)],sort_keys=True).encode())
            for fp,key in db.execute(select(Event.fingerprint,Incident.correlation_key).join(Incident,Incident.id==Event.incident_id).order_by(Event.fingerprint)):
                semantic.update((fp+key).encode())
            for key,n,explanation in db.execute(select(Incident.correlation_key,RiskEvaluation.event_count,RiskEvaluation.explanation)
                .join(Incident,Incident.id==RiskEvaluation.incident_id).order_by(Incident.correlation_key,RiskEvaluation.event_count)):
                semantic.update(json.dumps([key,n,json.loads(explanation)],sort_keys=True).encode())
            for raw_sha,n in db.execute(select(EventEvidence.raw_sha256,func.count()).group_by(EventEvidence.raw_sha256).order_by(EventEvidence.raw_sha256)):
                semantic.update((raw_sha+':'+str(n)).encode())
            evaluations=db.scalar(select(func.count()).select_from(RiskEvaluation))
            evidences=db.scalar(select(func.count()).select_from(EventEvidence))
        latency={key:percentiles(value) for key,value in samples.items()}
        acceptance=protocol['acceptance']
        checks={'no_errors':not errors,'import_count':imported==size,'duplicate_count':duplicates==size,
            'persisted_count':persisted==size,'six_types':kinds==6,
            'throughput':size/fresh_seconds>=acceptance['minimum_import_events_per_second'],
            'dashboard_p95':latency['dashboard']['p95']<=acceptance['maximum_dashboard_p95_seconds'],
            'report_p95':latency['report_creation']['p95']<=acceptance['maximum_report_creation_p95_seconds']}
        for format in ('json','csv','pdf'):
            entry=latency.get('export_'+format)
            checks['export_'+format]=bool(entry) and entry['p95']<=acceptance['maximum_export_p95_seconds']
        checks['resource_budget']=None if end_resource['peak_rss_bytes'] is None else end_resource['peak_rss_bytes']<=acceptance['maximum_observed_process_peak_rss_bytes']
        row={'events_requested':size,'seed':protocol['seed'],'synthetic_sha256':fingerprint(size,protocol['seed']),
            'request_records':min(size,1000),'import_requests':math.ceil(size/1000),'internal_batches':math.ceil(size/100),
            'imported':imported,'duplicates':duplicates,'persisted':persisted,'incidents':incidents,
            'semantic_sha256':semantic.hexdigest(),'risk_evaluations':evaluations,'evidence_appearances':evidences,
            'fresh_import_seconds':fresh_seconds,'events_per_second':size/fresh_seconds,
            'latencies_seconds':latency,'errors':errors,'sql':sql,
            'resources':{'before':start_resource,'after':end_resource,'cpu_process_delta_seconds':end_resource['cpu_process_seconds']-start_resource['cpu_process_seconds']},
            'acceptance':checks,'passed':all(v for v in checks.values() if v is not None),
            'retained_schema':schema if args.postgres_isolated else None}
        results['scenarios'].append(row);engine.dispose()
        print(json.dumps({'phase':args.phase,'size':size,'seconds':fresh_seconds,'events_per_second':row['events_per_second'],'passed':row['passed']}),flush=True)
    results['status']='completed'
    output.with_suffix('.json').write_text(json.dumps(results,indent=2,allow_nan=False),encoding='utf-8')
    with output.with_suffix('.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['phase','events','operation','samples','total_seconds','p50_seconds','p95_seconds','p99_seconds','fresh_events_per_second','errors','accepted'])
        for scenario in results['scenarios']:
            for name, values in scenario['latencies_seconds'].items():
                writer.writerow([args.phase,scenario['events_requested'],name,values['n'],values['total_seconds'],values['p50'],values['p95'],values['p99'],scenario['events_per_second'],len(scenario['errors']),scenario['passed']])
    return 0 if all(r['passed'] for r in results['scenarios']) else 1


if __name__=='__main__': raise SystemExit(main())
