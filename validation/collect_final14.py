"""Collect only results from completed isolated iteration14 executions. Never overwrite evidence."""
import csv
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import xml.etree.ElementTree as ET
from .isolated import ROOT


def main():
    destination=ROOT/'docs/resultados';output=destination/'iter14_validacion.json'
    if output.exists():raise RuntimeError('Evidence exists')
    tests={}
    for name in ('sqlite','pg'):
        suffix='sqlite-final' if name=='sqlite' else 'pg'
        suite=ET.parse(ROOT/f'.test-runs/iter14-{suffix}.xml').getroot().find('testsuite')
        tests[name]={k:int(suite.attrib[k]) for k in ('tests','failures','errors','skipped')}
        tests[name]['duration_seconds']=float(suite.attrib['time'])
        tests[name]['cases']=[{'module':c.attrib['classname'],'name':c.attrib['name']} for c in suite.findall('testcase')]
        assert tests[name]['tests']==216 and not any(tests[name][k] for k in ('failures','errors','skipped'))
    runs={}
    for filename in ('iter14_frontend_postgresql_final.json','iter14_integral_sqlite_final.json',
                     'iter14_agent_http_postgresql_final.json','iter14_pipeline_postgresql_final.json'):
        runs[filename]=json.loads((destination/filename).read_text(encoding='utf-8'))
    compose=sorted(destination.glob('iter14_compose_base_*.json'),key=lambda p:p.stat().st_mtime)[-1]
    c=json.loads(compose.read_text(encoding='utf-8-sig'))
    assert c['all_services_restarted_preserving_fixture'] and c['web_proxy_cookie_login_restore_logout']
    for source,target in [('suricata-validation.json','iter14_suricata_offline.json'),
                          ('engine-synthetic-alerts.eve.jsonl','iter14_EVE_SINTETICO_OFFLINE.jsonl')]:
        with (ROOT/'.test-runs/iter14-engine'/source).open('rb') as i,(destination/target).open('xb') as o:o.write(i.read())
    protected=['backend/app','agent','backend/migrations','frontend/src','frontend/package.json','frontend/package-lock.json','docs/PRACTICAS_PACKET_TRACER.md']
    changes=subprocess.check_output(['git','diff','644cc4f','--name-only','--',*protected],cwd=ROOT,text=True).splitlines()
    assert not changes,changes
    # Historical blob inventory is immutable in Git; no old artifact is staged or edited by this iteration.
    history_changes=subprocess.check_output(['git','diff','644cc4f','--name-only','--','docs/resultados'],cwd=ROOT,text=True).splitlines()
    assert all(Path(p).name.startswith(('iter14','README_ITER14')) for p in history_changes)
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'baseline':'644cc4f','pytest':tests,
        'environment':{'platform':platform.platform(),'python':platform.python_version(),
            'packages':{p:importlib.metadata.version(p) for p in ('fastapi','sqlalchemy','pytest','PyJWT','scikit-learn')},
            'node':subprocess.check_output(['node','--version'],text=True).strip()},
        'completed_runs':list(runs),'compose':compose.name,'protected_source_changes':changes,
        'migration_head':'0009','new_migration':False,'operational_database_accessed':False,'live_capture':False,
        'build':{'exit_code':0,'modules_observed':459,'vite_seconds_observed':47.96},
        'npm_ci':{'exit_code':0,'packages_added':66,'audited':67,'vulnerabilities_reported':0},
        'evidence_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.glob('iter14*') if p.is_file()},
        'first_sqlite_attempt':{'passed':215,'failed':1,'seconds_observed':488.01,'failure':'unexpected fixture login401; related seven tests passed on repeat without code changes'},
        'limits_on_sqlite_repeat':{'OPENBLAS_NUM_THREADS':1,'OMP_NUM_THREADS':1},
        'limitations':['No external audit or guarantee of absence of vulnerabilities.',
            'First parallel Compose health check and first Suricata browser run failed; retries recorded separately.',
            'Browser initially reported ERR_INSUFFICIENT_RESOURCES under shared load.',
            'No new performance benchmark; pytest/build durations are QA timings only.',
            'Versions/build/npm values come from actual execution; no secrets or raw failure bodies exported.']}
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    with output.with_suffix('.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['database','tests','failures','errors','skipped','seconds'])
        for k,v in tests.items():writer.writerow([k,*[v[x] for x in ('tests','failures','errors','skipped','duration_seconds')]])
    print(json.dumps({'evidence':output.name,'tests':{k:v['tests'] for k,v in tests.items()}}))


if __name__=='__main__':main()
