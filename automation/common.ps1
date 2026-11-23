$ErrorActionPreference = 'Stop'
function Read-LabConfig([string]$Path) {
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($key in @('repo','python','eve','state','runtime','password_file','username','sensor','api','web','distro','unit','compose_project')) {
        if (-not $c.$key -or "$($c.$key)" -match '["\r\n]') { throw 'Invalid local configuration' }
    }
    foreach ($key in @('repo','python','eve','state','runtime','password_file')) {
        if (-not [IO.Path]::IsPathRooted($c.$key)) { throw 'Absolute paths required' }
    }
    foreach ($key in @('api','web')) {
        $uri = [Uri]$c.$key
        if (-not $uri.IsLoopback -or $uri.Scheme -notin @('http','https') -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw 'Loopback URLs required' }
    }
    if ($c.unit -ne 'smartir-suricata.service' -or $c.distro -notmatch '^[a-zA-Z0-9_.-]+$' -or $c.compose_project -notmatch '^[a-z0-9_-]+$') { throw 'Invalid service configuration' }
    if ([int]$c.poll_seconds -lt 5 -or [int]$c.poll_seconds -gt 300) { throw 'Invalid polling interval' }
    if ([int]$c.docker_wait_seconds -lt 0 -or [int]$c.docker_wait_seconds -gt 180) {throw 'Invalid Docker wait'}
    return $c
}
function Test-LabHttp([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { return $false }
}
# Windows PowerShell 5.1 turns native stderr into RemoteException when
# ErrorActionPreference=Stop, even for successful docker compose operations.
# Temporarily tolerate native stderr; always check the native exit code.
function Invoke-LabNative([scriptblock]$Operation) {
    $previous=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue'
        & $Operation 2>$null | Out-Null
        return [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference=$previous
    }
}
function Invoke-LabCompose($c,[string[]]$Command) {
    $code=Invoke-LabNative {
        & docker compose --project-directory $c.repo -p $c.compose_project -f (Join-Path $c.repo 'compose.yaml') @Command
    }
    if ($code -ne 0) { throw 'Compose operation failed' }
}
function Invoke-LabUnit($c,[string]$Action) {
    $code=Invoke-LabNative {
        & wsl -d $c.distro --exec sudo -n /usr/bin/systemctl $Action $c.unit
    }
    if ($code -ne 0) { throw 'WSL service operation failed; check local sudo authorization and journal' }
}
function Test-LabUnit($c) {
    $code=Invoke-LabNative {
        & wsl -d $c.distro --exec /usr/bin/systemctl is-active --quiet $c.unit
    }
    return $code -eq 0
}
