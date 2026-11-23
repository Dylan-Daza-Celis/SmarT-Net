param([Parameter(Mandatory=$true)][string]$Config,[switch]$Remove)
. "$PSScriptRoot\common.ps1"
$null=Read-LabConfig $Config
$name='SmartIR-Lab-'+$env:USERNAME
if ($Remove) { Unregister-ScheduledTask -TaskName $name -Confirm:$false;exit }
$path=(Resolve-Path -LiteralPath $Config).Path
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -File "'+$PSScriptRoot+'\start.ps1" -Foreground -Config "'+$path+'"')
$principal=New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $name -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $principal.UserId) -Principal $principal -Settings $settings
