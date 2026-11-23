"""python -m validation.run_integral --database postgresql [--browser]."""
import argparse
import json
import os
import platform
import subprocess
import shutil
import time
from datetime import datetime, timezone
import httpx
from .isolated import Isolated, ROOT, port
from .journey import journey


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', choices=['sqlite', 'postgresql'], default='sqlite')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--label', default='final')
    parser.add_argument('--iteration', default='10', choices=['10','13','14'])
    args = parser.parse_args()
    if not args.label.replace('-', '').isalnum(): parser.error('Alphanumeric label required')
    output = ROOT/'docs/resultados'/f'iter{args.iteration}_integral_{args.database}_{args.label}.json'
    if output.exists(): parser.error('Evidence exists; choose a new label, historical results are immutable')
    isolated = Isolated(args.database)
    start = time.perf_counter()
    with isolated.running():
        with httpx.Client(base_url=isolated.base_url, trust_env=False, timeout=120) as client:
            result = journey(client, isolated.credentials)
            before = isolated.snapshot()
            isolated.stop(); isolated.start()
            assert isolated.snapshot() == before
            username, password = isolated.credentials['administrador']
            token = client.post('/api/auth/login', json={'username': username, 'password': password}).json()['access_token']
            headers = {'Authorization': 'Bearer '+token}
            for path in ('/api/ml/runs/'+result['ml_run_id'], '/api/evaluation/experiments/'+result['experiment_id']):
                assert client.get(path, headers=headers).status_code == 200
            for fmt, sha in result['export_sha256'].items():
                import hashlib
                response = client.get('/api/analytics/reports/'+result['report_id'], params={'format': fmt}, headers=headers)
                assert hashlib.sha256(response.content).hexdigest() == sha
        result.update(database=args.database, generated_at=datetime.now(timezone.utc).isoformat(),
                      transport='HTTP TCP loopback, real Uvicorn process', api_restart_preserved=True,
                      tables_before_after=before, python=platform.python_version(), platform=platform.platform())
        if args.browser:
            web_port = port()
            env = {**isolated.environment, 'VITE_API_URL': '', 'VALIDATION_API_TARGET': isolated.base_url,
                   'VALIDATION_WEB_PORT': str(web_port), 'VALIDATION_CREDENTIALS': json.dumps(isolated.credentials),
                   'VALIDATION_INCIDENT': result['incident_id'], 'VALIDATION_OUTPUT': str(isolated.directory/'browser-evidence')}
            # Credentials exist only in the child process environment; no trace/HAR or storageState.
            command = ['node', 'node_modules/@playwright/test/cli.js', 'test', '--config', 'tests/playwright.config.ts']
            completed = subprocess.run(command, cwd=ROOT/'frontend', env=env, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            (isolated.directory/'browser.log').write_text(completed.stdout, encoding='utf-8')
            print(completed.stdout, flush=True)
            completed.check_returncode()
            result['browser'] = json.loads((isolated.directory/'browser-evidence.browser.json').read_text(encoding='utf-8'))
            for source in isolated.directory.glob('browser-evidence.*'):
                destination = output.parent/(output.stem+source.name.removeprefix('browser-evidence'))
                if destination.exists(): raise RuntimeError('Refusing to overwrite existing browser evidence')
                shutil.copyfile(source, destination)
    result['duration_seconds'] = time.perf_counter()-start
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'evidence': str(output.relative_to(ROOT)), 'checks': len(result['checks']),
                      'restart_preserved': True, 'browser': args.browser}))


if __name__ == '__main__': main()
