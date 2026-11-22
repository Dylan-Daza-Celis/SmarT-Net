"""Deterministic Suricata-shaped synthetic records, never claimed as IDS capture."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import random

TYPES = ['acceso_no_autorizado', 'malware', 'dos', 'escaneo', 'uso_indebido', 'exfiltracion']
CATEGORIES = ['attempted-admin', 'trojan-activity', 'attempted-dos', 'network-scan', 'policy-violation', 'data-exfiltration']


def batches(count, seed=202609, batch_size=1000):
    if count not in (100, 1000, 10000) or not 1 <= batch_size <= 1000:
        raise ValueError('Use declared synthetic sizes and batch_size <= 1000')
    rng = random.Random(seed)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for start in range(0, count, batch_size):
        rows = []
        for i in range(start, min(count, start+batch_size)):
            group, member = divmod(i, 10)
            kind = group % 6
            rows.append({'timestamp': (base+timedelta(seconds=group*60+member)).isoformat(),
                'event_type': 'alert', 'src_ip': f'198.18.{group//250}.{group%250+1}',
                'dest_ip': f'192.0.2.{group%250+1}', 'src_port': rng.randrange(1024, 65536), 'dest_port': 443,
                'proto': 'TCP', 'flow_id': seed*100000+i,
                'alert': {'signature': f'ITER09 SYNTHETIC BENCHMARK ONLY {TYPES[kind]} {i}',
                          'signature_id': 1000000+kind, 'category': CATEGORIES[kind], 'severity': rng.randrange(1, 4)}})
        rng.shuffle(rows)  # Out-of-order event times, reproducible within each bounded request.
        yield b''.join((json.dumps(r, sort_keys=True, separators=(',', ':'))+'\n').encode() for r in rows)


def fingerprint(count, seed=202609):
    value = hashlib.sha256()
    for block in batches(count, seed): value.update(block)
    return value.hexdigest()
