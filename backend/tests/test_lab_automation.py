"""PowerShell orchestration tests: temporary files and mocked services; NEVER capture or launch Docker."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import os
import pytest

ROOT=Path(__file__).resolve().parents[2]
PS=shutil.which('powershell') or shutil.which('pwsh')
pytestmark=pytest.mark.skipif(not PS,reason='PowerShell not installed')

def invoke(script):
    return subprocess.run([PS,'-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=30)

def config(tmp_path):
    c=json.loads((ROOT/'automation/lab.example.json').read_text())
    c.update(repo=str(ROOT),python=sys.executable,eve=str(tmp_path/'eve.json'),state=str(tmp_path/'state'),runtime=str(tmp_path/'runtime'),password_file=str(tmp_path/'password'))
    c['docker_wait_seconds']=0
    path=tmp_path/'lab.json';path.write_text(json.dumps(c))
    return path,c

def test_all_powershell_files_parse():
    for path in (ROOT/'automation').glob('*.ps1'):
        r=invoke(f"$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$t,[ref]$e)>$null;if($e.Count){{exit 1}}")
        assert r.returncode==0,path.name

def test_stop_is_idempotent_and_preserves_inputs(tmp_path):
    path,c=config(tmp_path)
    for key in ('eve','password_file'):Path(c[key]).write_text('synthetic-preserve')
    for _ in range(2):assert invoke(f"& '{ROOT}/automation/stop.ps1' -Config '{path}'").returncode==0
    assert (Path(c['runtime'])/'stop.request').exists()
    assert (Path(c['runtime'])/'agent-stop.request').exists()
    assert all(Path(c[k]).read_text()=='synthetic-preserve' for k in ('eve','password_file'))

def test_unsafe_remote_configuration_fails_closed(tmp_path):
    path,c=config(tmp_path);c['api']='http://example.invalid';path.write_text(json.dumps(c))
    r=invoke(f"& '{ROOT}/automation/stop.ps1' -Config '{path}'")
    assert r.returncode!=0 and not Path(c['runtime']).exists()

def test_failed_docker_has_no_partial_start_or_secret_output(tmp_path):
    path,c=config(tmp_path)
    r=invoke(f"function docker {{$global:LASTEXITCODE=1}}; & '{ROOT}/automation/supervise.ps1' -Config '{path}'")
    s=json.loads((Path(c['runtime'])/'status.json').read_text(encoding='utf-8-sig'))
    assert s['last_failure']=='failed_inspect_local_components' and not s['agent_alive']
    assert 'password' not in r.stdout
    # The lock is released after failure and another attempt can diagnose Docker again.
    assert invoke(f"function docker {{$global:LASTEXITCODE=1}}; & '{ROOT}/automation/supervise.ps1' -Config '{path}'").returncode!=0

def test_concurrent_supervisor_refuses_owned_checkpoint(tmp_path):
    path,c=config(tmp_path);Path(c['state']).mkdir()
    lock=Path(c['state'])/'.lab-supervisor.lock'
    r=invoke(f"$h=[IO.File]::Open('{lock}','OpenOrCreate','ReadWrite','None');try {{ & '{ROOT}/automation/supervise.ps1' -Config '{path}' }} finally {{$h.Dispose()}}")
    assert 'already owns' in r.stdout
    assert not (Path(c['runtime'])/'status.json').exists()

def test_partial_start_stops_only_owned_compose(tmp_path):
    path,c=config(tmp_path);c['stop_owned_compose']=True;path.write_text(json.dumps(c))
    calls=tmp_path/'calls'
    stub=f"function docker {{[string]::Join(' ', $args)|Add-Content '{calls}';$global:LASTEXITCODE=0}};function Invoke-WebRequest {{[pscustomobject]@{{StatusCode=200}}}};function wsl {{$global:LASTEXITCODE=1}};"
    invoke(stub+f"& '{ROOT}/automation/supervise.ps1' -Config '{path}'")
    text=calls.read_text();assert 'up -d' in text and 'stop' in text and 'down' not in text

def test_agent_stop_file_exits_without_network_and_keeps_checkpoint(tmp_path):
    source=tmp_path/'eve.json';source.write_text('')
    stop=tmp_path/'stop';stop.touch();state=tmp_path/'state'
    env={**os.environ,'PYTHONPATH':str(ROOT/'agent'),'SMARTIR_AGENT_USERNAME':'synthetic-service',
         'SMARTIR_AGENT_PASSWORD':'synthetic-test-password-only','SMARTIR_AGENT_PASSWORD_FILE':''}
    r=subprocess.run([sys.executable,'-m','smartir_agent','--file',str(source),'--state-dir',str(state),
        '--api-url','http://127.0.0.1:1','--stop-file',str(stop)],env=env,capture_output=True,text=True,timeout=15)
    assert r.returncode==0 and '"code": "stopped"' in r.stdout
    assert (state/'state.db').exists() and source.exists() and 'synthetic-test-password-only' not in r.stdout

def test_stop_after_start_intent_is_not_lost(tmp_path):
    path,c=config(tmp_path);Path(c['runtime']).mkdir();(Path(c['runtime'])/'stop.request').touch()
    marker=tmp_path/'docker-was-called'
    r=invoke(f"function docker {{New-Item '{marker}'}}; & '{ROOT}/automation/supervise.ps1' -Config '{path}' -RequestedAt '2000-01-01T00:00:00Z'")
    assert not marker.exists()
