"""Sanitized iteration11 summary from actual JUnit and preserved Git artifacts."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from .isolated import ROOT


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='final');args=parser.parse_args()
    if not args.label.replace('-','').isalnum():parser.error('Alphanumeric label required')
    output=ROOT/'docs/resultados'/f'iter11_validacion_{args.label}.json'
    if output.exists():raise RuntimeError('Evidence already exists')
    tests={}
    for dialect in ('sqlite','pg'):
        file=ROOT/f'.test-runs/iter11-release-{dialect}.xml'
        suite=ET.parse(file).getroot().find('testsuite')
        tests[dialect]={key:int(suite.attrib[key]) for key in ('tests','failures','errors','skipped')}
        tests[dialect]['duration_seconds']=float(suite.attrib['time'])
        tests[dialect]['cases']=[{'module':c.attrib.get('classname'),'name':c.attrib['name'],'seconds':float(c.attrib['time'])} for c in suite.findall('testcase')]
    history={}
    tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
    for name in tracked:
        if not name.startswith('docs/resultados/') or Path(name).name.startswith('iter11'):continue
        previous=subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=ROOT,text=True).strip()
        actual=subprocess.check_output(['git','hash-object','--path='+name,name],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        history[name]={'git_object':previous,'unchanged':previous==actual}
    assert all(r['unchanged'] for r in history.values())
    algorithms={}
    for name in ('risk.py','correlation.py','suricata.py','ml_engine.py','ml_artifact.py','evaluation_metrics.py','experiments.py'):
        path='backend/app/'+name
        before=subprocess.check_output(['git','rev-parse','HEAD:'+path],cwd=ROOT,text=True).strip()
        now=subprocess.check_output(['git','hash-object','--path='+path,path],cwd=ROOT,text=True).strip()
        assert before==now
        algorithms[path]={'unchanged':True,'git_object':before}
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'git_parent':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'tests':tests,'historical_evidence':history,'algorithms':algorithms,'head':'0009',
        'migration':'additive users.eve_only default False; applied only to isolated test databases',
        'build':{'command':'npm run build','exit_code':0,'modules':442,'vite_seconds_observed':7.67,
                 'artifact_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()}},
        'notes':['Build values are transcribed from the successful tool output; artifact bytes independently hashed.',
                 'JUnit metadata only; no captured failure bodies, credentials or traces exported.',
                 'Historic comparison uses Git clean filters for CRLF/LF; no existing experimental result is rewritten.',
                 'No new Playwright run, real IDS traffic capture or external target tested in iteration11.']}
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'evidence':str(output.relative_to(ROOT)),'tests':{k:v['tests'] for k,v in tests.items()},'history_unchanged':len(history)}))


if __name__=='__main__':main()
