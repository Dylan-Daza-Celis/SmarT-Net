"""Publish a sanitized validation inventory from actual JUnit/audit/build artifacts."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from benchmarks.run_load import hardware
from .isolated import ROOT


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='final');args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Alphanumeric label only')
    target=ROOT/'docs/resultados'/f'iter10_validacion_{args.label}.json'
    if target.exists():parser.error('Evidence already exists')
    tests={}
    for dialect in ('sqlite','pg'):
        source=ROOT/f'.test-runs/iter10-release-{dialect}.xml'
        suite=ET.parse(source).getroot().find('testsuite')
        tests[dialect]={'tests':int(suite.attrib['tests']),'failures':int(suite.attrib['failures']),
                        'errors':int(suite.attrib['errors']),'skipped':int(suite.attrib['skipped']),
                        'duration_seconds':float(suite.attrib['time']),
                        'cases':[{'module':c.attrib.get('classname'),'name':c.attrib['name'],'seconds':float(c.attrib['time'])}
                                 for c in suite.findall('testcase')], 'source_sha256':sha(source)}
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    historical={}
    for name in tracked:
        if name.startswith('docs/resultados/') and not Path(name).name.startswith('iter10'):
            previous=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
            current=(ROOT/name).read_bytes()
            normalized=subprocess.check_output(['git','hash-object','--path='+name,name],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
            original=subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=ROOT,text=True).strip()
            historical[name]={'sha256':sha(ROOT/name),'raw_bytes_match_git_blob':current==previous,
                              'unchanged_from_parent':normalized==original}
    candidates=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    source_hashes={name:sha(ROOT/name) for name in candidates if (ROOT/name).is_file() and
                   (name.startswith(('backend/app/','backend/tests/','backend/migrations/','validation/','benchmarks/','frontend/src/','frontend/tests/'))
                    or name in ('frontend/package.json','frontend/package-lock.json','compose.yaml','backend/requirements.txt','backend/requirements-dev.txt'))}
    audits={}
    for key,file in [('npm','iter10-npm-audit-final.json'),('python_resolved','iter10-pip-audit-resolved.json')]:
        path=ROOT/'.test-runs'/file
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        destination=ROOT/'docs/resultados'/('iter10_auditoria_'+key+'.json')
        if destination.exists():
            if json.loads(destination.read_text(encoding='utf-8'))!=data:parser.error('Different audit evidence already published')
        else: destination.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        audits[key]={'evidence':str(destination.relative_to(ROOT)),
                    'vulnerabilities':data['metadata']['vulnerabilities'] if key=='npm' else sum(len(d['vulns']) for d in data['dependencies'])}
    evidence={'generated_at':datetime.now(timezone.utc).isoformat(),'git_parent':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'tests':tests,'hardware':hardware(),'versions':{pkg:version(pkg) for pkg in ('fastapi','starlette','sqlalchemy','alembic','scikit-learn','pytest','httpx')},
              'node':subprocess.check_output(['node','--version'],text=True).strip(),
              'migration_files':sorted(p.name for p in (ROOT/'backend/migrations/versions').glob('*.py')),
              'tracked_packet_tracer_files':[p for p in candidates if p.lower().endswith('.pkt')],
              'source_sha256':source_hashes,'historical_evidence':historical,'audits':audits,
              'build_artifacts':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'frontend/dist').rglob('*')) if p.is_file()},
              'notes':['JUnit times include suite setup/teardown; stdout totals can differ slightly.',
                       'Historical Git comparison uses clean filters (CRLF/LF on Windows); raw disk SHA-256 is separately recorded.',
                       'No user database content, JWT, credentials, raw bodies or password hashes are exported.',
                       'Browser and HTTP results live in their separate actual-run artifacts.']}
    target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'evidence':str(target.relative_to(ROOT)),'tests':{k:v['tests'] for k,v in tests.items()},
                      'historical_unchanged':all(v['unchanged_from_parent'] for v in historical.values())}))


if __name__=='__main__':main()
