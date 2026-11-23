param([string]$Config = "$PSScriptRoot\lab.local.json")
. "$PSScriptRoot\common.ps1"
$c=Read-LabConfig $Config
$owner='unknown';$handle=$null
if (Test-Path -LiteralPath $c.state -PathType Container) {
    try { $handle=[IO.File]::Open((Join-Path $c.state '.lab-supervisor.lock'),'OpenOrCreate','ReadWrite','None');$owner=$false }
    catch [UnauthorizedAccessException] { $owner='permission_denied' }
    catch { $owner=$true } finally { if ($handle) {$handle.Dispose()} }
}
$last=$null
try { $last=Get-Content (Join-Path $c.runtime 'status.json') -Raw | ConvertFrom-Json } catch {}
@{supervisor_lock_held=$owner;api_health=(Test-LabHttp ($c.api+'/health'));web_http=(Test-LabHttp $c.web);suricata_unit_active=(Test-LabUnit $c);eve_exists=(Test-Path -LiteralPath $c.eve);last_observation=$last} | ConvertTo-Json -Depth 4
