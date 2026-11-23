"""Sanitized iteration13 release evidence from real JUnit, browser outputs and Git history."""
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from .isolated import ROOT


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()


def main():
    target=ROOT/'docs/resultados/iter13_validacion.json'
    if target.exists():raise RuntimeError('Evidence exists; never overwrite')
    tests={}
    for dialect in ('sqlite','pg'):
        suite=ET.parse(ROOT/f'.test-runs/iter13-release-{dialect}.xml').getroot().find('testsuite')
        tests[dialect]={key:int(suite.attrib[key]) for key in ('tests','failures','errors','skipped')}
        tests[dialect]['duration_seconds']=float(suite.attrib['time'])
        tests[dialect]['cases']=[{'module':t.attrib['classname'],'name':t.attrib['name']} for t in suite.findall('testcase')]
        assert tests[dialect]['tests']==211 and not any(tests[dialect][k] for k in ('failures','errors','skipped'))
    browser={}
    for database,label in [('sqlite','estable'),('postgresql','capturas')]:
        path=ROOT/f'docs/resultados/iter13_frontend_{database}_{label}.json'
        item=json.loads(path.read_text(encoding='utf-8'));assert item['browser']['cases']==6 and not item['browser']['page_errors']
        browser[database]={'file':path.name,'cases':6,'browser':item['browser']['browser'],'checks':item['browser']['checks']}
    regression=ROOT/'docs/resultados/iter13_integral_postgresql_final.json'
    r=json.loads(regression.read_text(encoding='utf-8'));assert len(r['checks'])==61 and r['api_restart_preserved']
    suricata=ROOT/'docs/resultados/iter13_pipeline_postgresql_regresion.json'
    s=json.loads(suricata.read_text(encoding='utf-8'));assert s['receipt']['imported']==4 and s['repeat_import']['duplicates']==4
    assert not s['browser']['page_errors']
    compose=ROOT/'docs/resultados/iter13_compose_base_smartir-iter13-base-55afa103.json'
    c=json.loads(compose.read_text(encoding='utf-8-sig'));assert c['web_proxy_cookie_login_restore_logout'] and c['migration']=='0009'
    history={};preserved={}
    fixed={'risk.py','correlation.py','ingestion.py','eve_import.py','suricata.py','suricata_policy.py',
        'ml_engine.py','ml_artifact.py','ml_data.py','evaluation_data.py','experiments.py','evaluation_metrics.py',
        'models.py','schemas.py','analytics.py','analytical_reports.py','lifecycle.py','reassessment.py'}
    for path in git('ls-files').splitlines():
        if path.startswith('docs/resultados/'):destination=history
        elif path.startswith(('agent/','backend/migrations/')) or path in {'backend/app/'+s for s in fixed} or path in ('frontend/package.json','frontend/package-lock.json','backend/requirements.txt'):destination=preserved
        else:continue
        before=git('rev-parse','HEAD:'+path);after=git('hash-object','--path='+path,path)
        mode='git_clean_object'
        if before!=after:
            # Some iteration12 JSON was staged with text conversion before its -text attribute.
            # Do not rewrite that evidence or its index: prove line-ending equivalence explicitly.
            original=subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT)
            actual=(ROOT/path).read_bytes()
            assert destination is history and path.endswith('.json') and original.replace(b'\r\n',b'\n')==actual.replace(b'\r\n',b'\n'),path
            mode='same_content_crlf_lf_difference_only'
        destination[path]={'content_unchanged':True,'comparison':mode,'git_object':before}
    # Retain failure counts without publishing screenshots/DOM/logs that could include typed fixtures.
    attempts={}
    for name,directory in [('first','647c7cfd24f64581ab89b0beb4043258'),('second','0f74aed160f542a98bc405ba4de43f84'),
        ('third','d769ef5b6769471e8f44e50fd34ffb32'),('first_pass','42a6b037399a4a0bae9b909c1bebd6cb'),
        ('sqlite_transform_failure','7e172ded3eb64425a02ecf61d534b4c1')]:
        text=(ROOT/f'.test-runs/iter10-{directory}/frontend.log').read_text(encoding='utf-8')
        text=re.sub(r'\x1b\[[0-9;]*m','',text)
        passed=re.findall(r'\b(\d+) passed\b',text);failed=re.findall(r'\b(\d+) failed\b',text)
        attempts[name]={'passed':int(passed[-1]) if passed else 0,'failed':int(failed[-1]) if failed else 0,
            'log_sha256':hashlib.sha256(text.encode()).hexdigest()}
    artifacts=[p for p in (ROOT/'docs/resultados').glob('iter13*') if p.is_file()]
    sources=[p for p in (ROOT/'frontend/src').rglob('*') if p.is_file()]
    sources.extend(ROOT/p for p in ('backend/app/security.py','backend/app/main.py','backend/app/abuse.py','backend/app/web_session.py',
        'backend/tests/test_web_session.py','frontend/vite.config.ts','compose.yaml','frontend/tests/frontend13.spec.ts',
        'frontend/tests/frontend13.config.ts','frontend/tests/integral.spec.ts','frontend/tests/suricata12.spec.ts',
        'frontend/tests/vite.validation.ts','validation/run_frontend13.py','validation/collect_frontend13.py'))
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'git_baseline':git('rev-parse','HEAD'),
        'environment':{'platform':platform.platform(),'python':platform.python_version(),
            'node':subprocess.check_output(['node','--version'],text=True).strip(),'npm_observed':'10.8.2','postgresql':'16.16',
            'packages':{p:importlib.metadata.version(p) for p in ('fastapi','sqlalchemy','pytest','PyJWT','argon2-cffi')}},
        'pytest':tests,'browser':browser,'browser_cases_executed_final':14,'unique_browser_cases_final':8,
        'regressions':{'integral':{'file':regression.name,'api_checks':61,'restart_preserved':True,'browser_cases':1},
                       'suricata':{'file':suricata.name,'browser_cases':1,'imported':4,'duplicates':4}},
        'compose':{'file':compose.name,'cookie_proxy_validated':True},'attempts':attempts,
        'build':{'command':'npm run build','exit_code':0,'modules':459,'vite_seconds_observed':9.24,
            'artifacts':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()}},
        'npm_ci':{'exit_code':0,'packages_added_observed':66,'audited_observed':67,'known_vulnerabilities_reported':0},
        'historical_evidence':history,'preserved_code_and_dependencies':preserved,'migration_head':'0009','new_migration':False,
        'operational_data_read_or_written':False,'live_capture':False,'user_services_rebuilt':False,
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'evidence_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts},
        'limitations':['All browser/data fixtures are isolated and synthetic; no production/IDS validation.',
            'Chromium only; one network failure is deliberately aborted to test retry, not a measured server outage.',
            'JWT remains stateless; browser logout deletes cookie, does not revoke an already stolen copy.',
            'Package audit is npm ci output only, not an external security audit.',
            'Build/module/npm figures transcribed from actual successful tool output; JUnit is parsed directly.',
            'Historical Git comparison uses clean filters; pre-existing JSON CRLF/LF differences are recorded explicitly, never rewritten. Raw source hashes may differ after CRLF conversion.',
            'Evidence files from earlier successful iteration13 attempts remain marked as intermediate.']}
    with target.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    with target.with_suffix('.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['suite','cases','failures','errors','skipped','duration_seconds'])
        for name,suite in tests.items():writer.writerow([name,*[suite[k] for k in ('tests','failures','errors','skipped','duration_seconds')]])
        for name in browser:writer.writerow(['browser_'+name,6,0,0,0,'not_recorded'])
        writer.writerow(['browser_integral',1,0,0,0,'not_recorded']);writer.writerow(['browser_suricata',1,0,0,0,'not_recorded'])
    print(json.dumps({'evidence':str(target.relative_to(ROOT)),'pytest_per_database':211,'browser_cases_final':14,
        'historical_artifacts_unchanged':len(history),'preserved_source_files':len(preserved)}))


if __name__=='__main__':main()
