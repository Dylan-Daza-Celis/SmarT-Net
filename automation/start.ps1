param([string]$Config = "$PSScriptRoot\lab.local.json", [switch]$Foreground)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\common.ps1"
$null=Read-LabConfig $Config
$absolute=(Resolve-Path -LiteralPath $Config).Path
if ($Foreground) { & "$PSScriptRoot\supervise.ps1" -Config $absolute; exit $LASTEXITCODE }
# Supervisor owns the exclusive checkpoint lock BEFORE any service or reader starts.
$arguments='-NoProfile -File "'+$PSScriptRoot+'\supervise.ps1" -Config "'+$absolute+'" -RequestedAt "'+[DateTimeOffset]::UtcNow.ToString('o')+'"'
$null=Start-Process powershell.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru
Write-Output 'Start requested. Use status.ps1 to verify actual readiness.'
