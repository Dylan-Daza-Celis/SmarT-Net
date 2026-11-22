"""Flatten already executed paired JSON measurements; no new timings or estimates."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs/resultados/iter09_mediciones_pareadas.csv'


def main():
    if OUTPUT.exists(): raise ValueError('Summary already exists; retain historical measurements')
    columns=['source_file','database','phase','events','operation','samples','total_seconds','p50_seconds','p95_seconds',
        'p99_seconds','fresh_events_per_second','records_per_import_request','import_requests','internal_batches',
        'imported','duplicates','persisted','incidents','risk_evaluations','evidence_appearances','http_errors',
        'cpu_process_delta_seconds','process_peak_rss_bytes','acceptance_passed']
    with OUTPUT.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for path in sorted((ROOT/'docs/resultados').glob('iter09_*_paired.json')):
            run=json.loads(path.read_text())
            if run['status']!='completed':raise ValueError('Incomplete source')
            for case in run['scenarios']:
                for operation,latency in case['latencies_seconds'].items():
                    writer.writerow({'source_file':path.name,'database':run['environment']['database'],'phase':run['phase'],
                        'events':case['events_requested'],'operation':operation,'samples':latency['n'],
                        'total_seconds':latency['total_seconds'],'p50_seconds':latency['p50'],'p95_seconds':latency['p95'],'p99_seconds':latency['p99'],
                        'fresh_events_per_second':case['events_per_second'],'records_per_import_request':case['request_records'],
                        'import_requests':case['import_requests'],'internal_batches':case['internal_batches'],'imported':case['imported'],
                        'duplicates':case['duplicates'],'persisted':case['persisted'],'incidents':case['incidents'],
                        'risk_evaluations':case['risk_evaluations'],'evidence_appearances':case['evidence_appearances'],
                        'http_errors':len(case['errors']),'cpu_process_delta_seconds':case['resources']['cpu_process_delta_seconds'],
                        'process_peak_rss_bytes':case['resources']['after']['peak_rss_bytes'],'acceptance_passed':case['passed']})


if __name__=='__main__':main()
