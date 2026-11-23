"""Run INSIDE Ubuntu WSL: configuration test and synthetic offline PCAP only, never a live interface."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.suricata_alerts_config import create, verify
from validation.synthetic_icmp import make_pcap


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    if args.output_dir.exists():raise SystemExit('Output exists; choose a fresh isolated directory')
    os.umask(0o077)
    workspace=Path(tempfile.mkdtemp(prefix='smartir-iter12-offline-'))
    version=subprocess.check_output(['suricata','-V'],text=True).strip()
    if '8.0.3' not in version:raise SystemExit('This validation protocol requires the declared Suricata 8.0.3')
    base=workspace/'base.yaml';shutil.copyfile(ROOT/'config/suricata/lab-base.yaml',base)
    rule=workspace/'synthetic.rules';shutil.copyfile(ROOT/'config/suricata/lab-icmp.rules',rule)
    packet=workspace/'SYNTHETIC-NOT-CAPTURE.pcap';packet.write_bytes(make_pcap())
    derived=workspace/'with-smartir-alerts.yaml'
    original=base.read_bytes();config_result=create(base,derived)
    verify(derived)
    for name,flags in [('config_test',['-T']),('offline_replay',['-r',str(packet),'--runmode','single'])]:
        command=['suricata','-c',str(derived),'-S',str(rule),'-l',str(workspace),'--init-errors-fatal',*flags]
        completed=subprocess.run(command,cwd=workspace,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (workspace/(name+'.log')).write_text(completed.stdout,encoding='utf-8')
        if completed.returncode:raise SystemExit(f'{name} failed (exit {completed.returncode}); private diagnostics retained in {workspace}')
    assert base.read_bytes()==original
    general=[json.loads(s) for s in (workspace/'eve-general.json').read_text().splitlines() if s.strip()]
    alerts=[json.loads(s) for s in (workspace/'smartir-alerts.json').read_text().splitlines() if s.strip()]
    assert len(alerts)==4 and all(a['event_type']=='alert' for a in alerts)
    assert all(a['alert']['signature']=='SMARTIR WSL2 LAB ICMP TEST' and a['alert']['severity']==3 and
               a['alert'].get('category') in ('',None) for a in alerts)
    assert sum(a['event_type']=='alert' for a in general)==4
    args.output_dir.mkdir(parents=True,exist_ok=False)
    # These records are engine-generated from a synthetic PCAP, NOT live captured traffic.
    shutil.copyfile(workspace/'smartir-alerts.json',args.output_dir/'engine-synthetic-alerts.eve.jsonl')
    result={'version':version,'os':platform.platform(),'uid':os.getuid(),'protocol':'suricata8.0.3-synthetic-offline-v1',
            'config_test_exit':0,'offline_replay_exit':0,'live_interface_opened':False,'user_config_read_or_written':False,
            'synthetic_packets':4,'general_event_types':dict(Counter(a['event_type'] for a in general)),
            'dedicated_event_types':dict(Counter(a['event_type'] for a in alerts)),
            'source_pcap_sha256':hashlib.sha256(packet.read_bytes()).hexdigest(),
            'source_alerts_sha256':hashlib.sha256((workspace/'smartir-alerts.json').read_bytes()).hexdigest(),
            'base_unchanged':base.read_bytes()==original,'configuration':config_result,
            'capture_class':'engine-generated alerts from deterministic offline synthetic PCAP; no live capture'}
    (args.output_dir/'suricata-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
