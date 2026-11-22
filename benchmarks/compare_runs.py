"""Compare actual benchmark files; never generates or substitutes measurements."""
import argparse
import csv
import json
from pathlib import Path


def compare(before, after):
    if before['status']!='completed' or after['status']!='completed':raise ValueError('Incomplete run')
    for key in ('seed','sizes','events_per_incident','correlation_window_seconds','eve_records_per_request','dashboard_samples','report_creation_samples','concurrency'):
        if before['protocol'][key]!=after['protocol'][key]:raise ValueError('Protocols differ: '+key)
    left={r['events_requested']:r for r in before['scenarios']};right={r['events_requested']:r for r in after['scenarios']}
    if set(left)!=set(right):raise ValueError('Scenario sets differ')
    rows=[]
    for count in sorted(left):
        a,b=left[count],right[count]
        identity=all(a.get(key) is not None and a[key]==b.get(key) for key in (
            'synthetic_sha256','semantic_sha256','imported','duplicates','persisted','incidents','risk_evaluations','evidence_appearances'))
        rows.append({'events':count,'semantic_identity':identity,'baseline_seconds':a['fresh_import_seconds'],
            'optimized_seconds':b['fresh_import_seconds'],'baseline_events_per_second':a['events_per_second'],
            'optimized_events_per_second':b['events_per_second'],
            'observed_throughput_ratio':b['events_per_second']/a['events_per_second'],
            'baseline_sql_statements':a['sql']['import']['statements'],'optimized_sql_statements':b['sql']['import']['statements'],
            'baseline_dashboard_p95':a['latencies_seconds']['dashboard']['p95'],
            'optimized_dashboard_p95':b['latencies_seconds']['dashboard']['p95'],
            'baseline_report_p95':a['latencies_seconds']['report_creation']['p95'],
            'optimized_report_p95':b['latencies_seconds']['report_creation']['p95'],
            'baseline_export_pdf_p95':a['latencies_seconds']['export_pdf']['p95'],
            'optimized_export_pdf_p95':b['latencies_seconds']['export_pdf']['p95'],
            'both_acceptance_budgets_passed':a['passed'] and b['passed']})
    return {'kind':'descriptive_synthetic_before_after','scenarios':rows,
        'passed':all(r['semantic_identity'] and r['both_acceptance_budgets_passed'] for r in rows),
        'limitations':['Single run per phase, shared host; no statistical significance or network generalization',
                       'Small p95/p99 samples; HTTP TCP excluded, PostgreSQL loopback IO included',
                       'Ingestion throughput is not MTTD, MTTR or measured human response']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.with_suffix('.json').exists() or args.output.with_suffix('.csv').exists():parser.error('Output already exists')
    result=compare(json.loads(args.before.read_text()),json.loads(args.after.read_text()))
    result.update(before=args.before.name,after=args.after.name)
    args.output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    with args.output.with_suffix('.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(result['scenarios'][0]));writer.writeheader();writer.writerows(result['scenarios'])
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
