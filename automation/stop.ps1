param([string]$Config = "$PSScriptRoot\lab.local.json")
. "$PSScriptRoot\common.ps1"
$c=Read-LabConfig $Config
New-Item -ItemType Directory -Force -Path $c.runtime | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $c.runtime 'stop.request') | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $c.runtime 'agent-stop.request') | Out-Null
Write-Output 'Controlled stop requested. Check status; no PID is killed and no data is deleted.'
