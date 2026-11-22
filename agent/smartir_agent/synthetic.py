"""Deterministic EVE-shaped lab file writer. Does not capture or generate network traffic."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import time

CATEGORIES = ('attempted-admin', 'trojan-activity', 'attempted-dos', 'network-scan', 'policy-violation', 'data-exfiltration')


def record(index, seed=202611):
    rng = random.Random(seed+index)
    return {'timestamp':(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=index)).isoformat(),
            'event_type':'alert', 'src_ip':f'198.18.0.{index%6+1}', 'dest_ip':'192.0.2.10',
            'src_port':rng.randrange(1024,65536), 'dest_port':443, 'proto':'TCP', 'flow_id':seed*100000+index,
            'alert':{'signature':f'ITER11 SYNTHETIC FILE REPLAY ONLY {index}', 'signature_id':1100000+index%6,
                     'category':CATEGORIES[index%6], 'severity':rng.randrange(1,4)}}


def line(index, seed=202611):
    return (json.dumps(record(index,seed), sort_keys=True, separators=(',',':'))+'\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--count', type=int, default=60)
    parser.add_argument('--seed', type=int, default=202611)
    parser.add_argument('--start-index', type=int, default=0)
    parser.add_argument('--interval', type=float, default=.2)
    parser.add_argument('--append', action='store_true')
    args = parser.parse_args()
    if not (1 <= args.count <= 10000 and 0 <= args.seed < 2**32 and args.start_index >= 0 and 0 <= args.interval <= 60):
        parser.error('Invalid bounded synthetic scenario')
    with args.file.open('ab' if args.append else 'xb') as stream:
        for index in range(args.start_index, args.start_index+args.count):
            stream.write(line(index,args.seed)); stream.flush(); os.fsync(stream.fileno())
            if args.interval: time.sleep(args.interval)


if __name__ == '__main__': main()
