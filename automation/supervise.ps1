param([Parameter(Mandatory=$true)][string]$Config,[string]$RequestedAt)
. "$PSScriptRoot\common.ps1"
$c=Read-LabConfig $Config
$lock=$null;$agent=$null;$unitOwned=$false;$composeOwned=$false;$healthy=$false;$lastFailure=$null
$stop=Join-Path $c.runtime 'stop.request'
$agentStop=Join-Path $c.runtime 'agent-stop.request'
$status=Join-Path $c.runtime 'status.json'
$intent=if ($RequestedAt) { [DateTimeOffset]::Parse($RequestedAt).UtcDateTime } else { [DateTime]::UtcNow }
New-Item -ItemType Directory -Force -Path $c.state,$c.runtime | Out-Null
try { $lock=[IO.File]::Open((Join-Path $c.state '.lab-supervisor.lock'),'OpenOrCreate','ReadWrite','None') }
catch { Write-Output 'Supervisor already owns this checkpoint or lock unavailable'; exit 2 }
function Record([string]$Code) {
    if ($Code -eq 'failed_inspect_local_components') {$script:lastFailure=$Code}
    @{at=[DateTimeOffset]::UtcNow.ToString('o');code=$Code;last_failure=$lastFailure;pid=$PID;api=$healthy;agent_alive=($null -ne $agent -and -not $agent.HasExited)} | ConvertTo-Json | Set-Content -LiteralPath $status -Encoding UTF8
    ('{0} {1}' -f [DateTimeOffset]::UtcNow.ToString('o'),$Code) | Add-Content -LiteralPath (Join-Path $c.runtime 'supervisor.log')
}
try {
    if ((Test-Path -LiteralPath $stop) -and (Get-Item -LiteralPath $stop).LastWriteTimeUtc -lt $intent) { Remove-Item -LiteralPath $stop }
    if (Test-Path -LiteralPath $agentStop) { Remove-Item -LiteralPath $agentStop }
    if (Test-Path -LiteralPath $stop) { Record 'cancelled_before_start';return }
    Record 'starting'
    $dockerDeadline=[DateTimeOffset]::UtcNow.AddSeconds([int]$c.docker_wait_seconds)
    do { & docker info *> $null; if ($LASTEXITCODE -eq 0 -or (Test-Path $stop)) {break}; if ([DateTimeOffset]::UtcNow -ge $dockerDeadline) {break};Start-Sleep -Seconds 2 } while ($true)
    if ($LASTEXITCODE -ne 0) { throw 'docker_unavailable' }
    if (Test-Path $stop) {Record 'cancelled_before_compose';return}
    # Never stop services that were already running when this supervisor started.
    $running=& docker compose --project-directory $c.repo -p $c.compose_project -f (Join-Path $c.repo 'compose.yaml') ps --status running -q 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'compose_inspection_failed' }
    $composeOwned= -not [bool]$running
    Invoke-LabCompose $c @('up','-d')
    $deadline=[DateTimeOffset]::UtcNow.AddSeconds(120)
    do { $healthy=Test-LabHttp ($c.api+'/health'); if ($healthy -and (Test-LabHttp $c.web)) { break }; Start-Sleep -Seconds 2 } while ([DateTimeOffset]::UtcNow -lt $deadline -and -not (Test-Path $stop))
    if (-not $healthy -or -not (Test-LabHttp $c.web) -or (Test-Path $stop)) { throw 'services_not_ready' }
    if (-not (Test-LabUnit $c)) { Invoke-LabUnit $c 'start';$unitOwned=$true }
    $eveDeadline=[DateTimeOffset]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $c.eve -PathType Leaf) -and [DateTimeOffset]::UtcNow -lt $eveDeadline -and -not (Test-Path $stop)) {Start-Sleep -Seconds 1}
    if (-not (Test-LabUnit $c) -or -not (Test-Path -LiteralPath $c.eve -PathType Leaf)) { throw 'sensor_not_ready' }
    if (-not (Test-Path -LiteralPath $c.password_file -PathType Leaf)) { throw 'password_file_missing' }
    $env:PYTHONPATH=Join-Path $c.repo 'agent'
    $env:SMARTIR_AGENT_USERNAME=$c.username;$env:SMARTIR_AGENT_PASSWORD_FILE=$c.password_file
    $env:SMARTIR_AGENT_PASSWORD=''
    $argsText='-m smartir_agent --file "'+$c.eve+'" --state-dir "'+$c.state+'" --api-url "'+$c.api+'" --sensor "'+$c.sensor+'" --stop-file "'+$agentStop+'"'
    $agent=Start-Process -FilePath $c.python -ArgumentList $argsText -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $c.runtime 'agent-current.log') -RedirectStandardError (Join-Path $c.runtime 'agent-current.err')
    while (-not (Test-Path -LiteralPath $stop)) {
        if ($agent.HasExited) { throw 'agent_exited_no_automatic_restart' }
        $healthy=Test-LabHttp ($c.api+'/health')
        Record $(if ($healthy -and (Test-LabUnit $c)) {'running'} else {'degraded'})
        Start-Sleep -Seconds $c.poll_seconds
    }
} catch { Record 'failed_inspect_local_components' }
finally {
    if ($agent -and -not $agent.HasExited) { New-Item -ItemType File -Force -Path $agentStop | Out-Null; while (-not $agent.WaitForExit(60000)) { Record 'agent_shutdown_pending_no_force_kill' } }
    if ($unitOwned) { try { Invoke-LabUnit $c 'stop' } catch { Record 'sensor_stop_failed' } }
    if ($composeOwned -and $c.stop_owned_compose) { try { Invoke-LabCompose $c @('stop') } catch { Record 'compose_stop_failed' } }
    Record 'supervisor_stopped';$lock.Dispose()
}
if ($lastFailure) {exit 1}
