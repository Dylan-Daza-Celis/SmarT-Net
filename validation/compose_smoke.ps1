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
    [ordered]@{generated_at=[DateTimeOffset]::UtcNow.ToString('o');project=$project;health=$health;web_http=$web.StatusCode;
        migration=$ExpectedHead;postgresql=$pg;data_kind='empty isolated test volume';browser_tested_in_this_compose=$false;
        scope='startup, migration, health and web HTTP only; independent browser/API journey uses isolated runner';
        original_services_modified=$false;volumes_removed=$false} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidence -Encoding utf8
    Write-Output "Evidence: $evidence"
} finally {
    if ($started) { & docker @arguments stop }
    $env:DB_PASSWORD = $priorDb
    $env:JWT_SECRET = $priorJwt
}
