param([string]$ExpectedHead = '0009', [ValidatePattern('^\d{2}$')][string]$Iteration = '11')
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $taskRoot
$project = "smartir-iter$Iteration-base-" + [guid]::NewGuid().ToString('N').Substring(0,8)
$evidence = Join-Path $taskRoot "docs/resultados/iter${Iteration}_compose_base_$project.json"
# Ephemeral values for a NEW empty volume only. Never read or edit the user's .env.
$priorDb = $env:DB_PASSWORD
$priorJwt = $env:JWT_SECRET
$env:DB_PASSWORD = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$env:JWT_SECRET = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$arguments = @('compose','-p',$project,'-f','compose.yaml','-f','validation/compose.validation.yaml')
$started = $false
try {
    & docker @arguments config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed' }
    & docker @arguments up --build -d
    if ($LASTEXITCODE -ne 0) { throw 'Isolated Compose startup failed' }
    $started = $true
    $health = $null
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        try { $health = Invoke-RestMethod 'http://127.0.0.1:58010/health'; break } catch { Start-Sleep -Seconds 1 }
    }
    if ($health.status -ne 'ok') { throw 'Isolated /health failed' }
    $web = Invoke-WebRequest 'http://127.0.0.1:55180/' -UseBasicParsing
    $migration = (& docker @arguments exec -T api python -m alembic current 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $migration -notmatch [regex]::Escape($ExpectedHead)) { throw 'Unexpected migration' }
    $pg = (& docker @arguments exec -T db psql -U smartir -d smartir -Atc 'SHOW server_version' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL version check failed' }
    $webCookieValidated = $false
    if ($Iteration -in @('13','14')) {
        # Account exists ONLY in this new project volume. Pass the random fixture via stdin, never command arguments.
        $taskPassword = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
        $taskPayload = @{username='validation_compose_13';password=$taskPassword} | ConvertTo-Json -Compress
        $taskScript = "import json,sys`nfrom app.database import Session`nfrom app.models import User`nfrom app.security import password_hasher`nd=json.load(sys.stdin)`nwith Session.begin() as db:`n db.add(User(username=d['username'],role='observador',password_hash=password_hasher.hash(d['password'])))"
        $taskPayload | & docker @arguments exec -T api python -c $taskScript
        if ($LASTEXITCODE -ne 0) { throw 'Isolated web fixture creation failed' }
        $taskWebSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $taskHeaders = @{Origin='http://127.0.0.1:55180';'X-SmartIR-CSRF'='1'}
        $taskLogin = Invoke-WebRequest 'http://127.0.0.1:55180/api/auth/session' -Method Post -ContentType 'application/json' -Body $taskPayload -Headers $taskHeaders -WebSession $taskWebSession -UseBasicParsing
        $taskIdentity = $taskLogin.Content | ConvertFrom-Json
        if ($taskIdentity.user.role -ne 'observador' -or $taskIdentity.PSObject.Properties.Name -contains 'access_token' -or $taskLogin.Headers['Set-Cookie'] -notmatch 'HttpOnly') { throw 'Unexpected cookie login contract' }
        if ($Iteration -eq '14') {
            & docker @arguments restart db api web
            if ($LASTEXITCODE -ne 0) { throw 'Isolated restart failed' }
            $taskReady = $false
            for ($taskAttempt=0; $taskAttempt -lt 60; $taskAttempt++) {
                try { $taskHealth = Invoke-RestMethod 'http://127.0.0.1:58010/health'; if ($taskHealth.status -eq 'ok') { $taskReady = $true; break } } catch {}
                Start-Sleep -Seconds 1
            }
            if (-not $taskReady) { throw 'Restart health failed' }
            $taskCount = (& docker @arguments exec -T db psql -U smartir -d smartir -Atc 'SELECT count(*) FROM users' | Out-String).Trim()
            if ($taskCount -ne '1') { throw 'Isolated user not preserved' }
        }
        $taskRestored = Invoke-RestMethod 'http://127.0.0.1:55180/api/auth/session' -WebSession $taskWebSession
        if ($taskRestored.user.id -ne $taskIdentity.user.id -or $taskRestored.expires_at -ne $taskIdentity.expires_at) { throw 'Proxy cookie restoration failed' }
        $taskLogout = Invoke-WebRequest 'http://127.0.0.1:55180/api/auth/session' -Method Delete -Headers $taskHeaders -WebSession $taskWebSession -UseBasicParsing
        if ($taskLogout.StatusCode -ne 204) { throw 'Cookie logout failed' }
        $taskUnauthorized = $false
        try { $null = Invoke-WebRequest 'http://127.0.0.1:55180/api/auth/session' -WebSession $taskWebSession -UseBasicParsing }
        catch { if ([int]$_.Exception.Response.StatusCode -eq 401) { $taskUnauthorized = $true } else { throw } }
        if (-not $taskUnauthorized) { throw 'Cookie remained authenticated after logout' }
        $webCookieValidated = $true
    }
    [ordered]@{generated_at=[DateTimeOffset]::UtcNow.ToString('o');project=$project;health=$health;web_http=$web.StatusCode;
        migration=$ExpectedHead;postgresql=$pg;data_kind=$(if ($Iteration -in @('13','14')) {'new isolated test volume with one temporary observer fixture'} else {'empty isolated test volume'});browser_tested_in_this_compose=$false;
        scope='startup, migration, health and web HTTP; iteration13 also tests cookie login/restore/logout via web proxy. Browser uses independent isolated runner';
        web_proxy_cookie_login_restore_logout=$webCookieValidated;all_services_restarted_preserving_fixture=($Iteration -eq '14');
        original_services_modified=$false;volumes_removed=$false} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidence -Encoding utf8
    Write-Output "Evidence: $evidence"
} finally {
    if ($started) { & docker @arguments stop }
    $env:DB_PASSWORD = $priorDb
    $env:JWT_SECRET = $priorJwt
}
