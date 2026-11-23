param([string]$Config = "$PSScriptRoot\lab.local.json")
. "$PSScriptRoot\common.ps1"
$c=Read-LabConfig $Config
& "$PSScriptRoot\stop.ps1" -Config $Config
$deadline=[DateTimeOffset]::UtcNow.AddSeconds(90);$released=$false
do {
    try {$h=[IO.File]::Open((Join-Path $c.state '.lab-supervisor.lock'),'OpenOrCreate','ReadWrite','None');$h.Dispose();$released=$true;break} catch {Start-Sleep -Seconds 1}
} while ([DateTimeOffset]::UtcNow -lt $deadline)
if (-not $released) {throw 'Previous supervisor still owns checkpoint; refusing duplicate start'}
& "$PSScriptRoot\start.ps1" -Config $Config
