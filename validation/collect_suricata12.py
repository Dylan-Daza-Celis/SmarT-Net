"""Sanitize actual iteration12 evidence; never overwrite earlier experimental results."""
import csv
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from .isolated import ROOT


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()


def main():
    target=ROOT/'docs/resultados/iter12_validacion_final.json'
    if target.exists():raise RuntimeError('Evidence exists; do not overwrite')
    suites={}
    for dialect in ('sqlite','pg'):
        suite=ET.parse(ROOT/f'.test-runs/iter12-release2-{dialect}.xml').getroot().find('testsuite')
        suites[dialect]={key:int(suite.attrib[key]) for key in ('tests','failures','errors','skipped')}
        suites[dialect]['duration_seconds']=float(suite.attrib['time'])
        suites[dialect]['cases']=[{'module':c.attrib['classname'],'name':c.attrib['name'],
                                  'seconds':float(c.attrib['time'])} for c in suite.findall('testcase')]
        assert suites[dialect]['tests']==198 and not any(suites[dialect][k] for k in ('failures','errors','skipped'))
    tracked=git('ls-files').splitlines()
    historical={}
    preserved={}
    algorithms={'risk.py','correlation.py','ingestion.py','eve_import.py','ml_engine.py','ml_artifact.py',
                'evaluation_metrics.py','experiments.py'}
    for name in tracked:
        if name.startswith('docs/resultados/'):
            destination=historical
        elif name.startswith(('agent/','backend/migrations/')) or name in {'backend/app/'+a for a in algorithms}:
            destination=preserved
        else:continue
        before=git('rev-parse','HEAD:'+name);now=git('hash-object','--path='+name,name)
        assert before==now,name
        destination[name]={'git_object':before,'unchanged':True}
    copies={}
    for number in (1,2):
        directory=ROOT/f'.test-runs/iter12-wsl-engine-{number}'
        for source,newname in [('engine-synthetic-alerts.eve.jsonl',f'iter12_eve_SINTETICO_OFFLINE_motor_{number}.jsonl'),
                               ('suricata-validation.json',f'iter12_suricata803_offline_{number}.json')]:
            path=ROOT/'docs/resultados'/newname
            if path.exists():raise RuntimeError('Evidence exists')
            shutil.copyfile(directory/source,path)
            copies[newname]=hashlib.sha256(path.read_bytes()).hexdigest()
    compose=list((ROOT/'docs/resultados').glob('iter12_compose_base_*.json'))
    assert len(compose)==1
    compose_result=json.loads(compose[0].read_text(encoding='utf-8-sig'))
    assert compose_result['migration']=='0009' and compose_result['health']['status']=='ok' and compose_result['web_http']==200
    browser=json.loads((ROOT/'docs/resultados/iter12_pipeline_postgresql_interfaz.browser.json').read_text(encoding='utf-8'))
    assert not browser['page_errors'] and browser['live_capture'] is False
    sources=[p for group in ('config/suricata','tools') for p in (ROOT/group).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    sources.extend(ROOT/p for p in ('backend/app/suricata.py','backend/app/suricata_policy.py','backend/tests/test_suricata12.py',
        'frontend/src/SuricataEventDetails.tsx','validation/synthetic_icmp.py','validation/suricata_offline_wsl.py',
        'validation/run_suricata12.py','validation/collect_suricata12.py','frontend/tests/suricata12.spec.ts',
        'frontend/tests/suricata12.config.ts'))
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'git_parent':git('rev-parse','HEAD'),
        'environment':{'platform':platform.platform(),'python':platform.python_version(),
            'packages':{p:importlib.metadata.version(p) for p in ('fastapi','sqlalchemy','pytest','psycopg','PyYAML')},
            'postgresql':'16.16 (isolated postgres:16-alpine)',
            'compose':subprocess.check_output(['docker','compose','version','--short'],text=True).strip()},
        'tests':suites,'historical_evidence':historical,'preserved_code':preserved,
        'head':'0009','new_migration':False,'operational_database_read_or_written':False,
        'build':{'command':'npm run build','exit_code':0,'modules':443,'vite_seconds_observed':6.52,
            'artifacts':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()}},
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'copied_evidence_sha256':copies,'compose_evidence':compose[0].name,'browser':browser,
        'notes':['Build duration/modules transcribed from successful tool output; output bytes hashed separately.',
            'Full suites include 34 new parametrized cases and historical regressions.',
            'JUnit metadata only: no test stdout or failure bodies exported.',
            'Suricata ran -T and -r synthetic PCAP, never a live capture interface.',
            'Existing operational four alerts were not read, reclassified or rewritten.',
            'Source hashes are raw working-file bytes; Git may normalize source line endings. Evidence JSONL/CSV preserve bytes.',
            'Prior experimental results are compared using Git clean filters; no historical result is replaced.']}
    with target.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    with target.with_suffix('.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['database','tests','failures','errors','skipped','duration_seconds'])
        for name,suite in suites.items():writer.writerow([name,*[suite[k] for k in ('tests','failures','errors','skipped','duration_seconds')]])
    print(json.dumps({'evidence':str(target.relative_to(ROOT)),'tests':{k:v['tests'] for k,v in suites.items()},
                      'historical_artifacts_unchanged':len(historical),'preserved_code_files':len(preserved)}))


if __name__=='__main__':main()
