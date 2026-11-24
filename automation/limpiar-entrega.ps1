# Elimina solamente carpetas y respaldos temporales conocidos de la copia local.
# No modifica .git, .env, .venv, secrets, volúmenes Docker, WSL ni el estado EVE.
[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='Low')]
param()

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not (Test-Path -LiteralPath (Join-Path $repo 'compose.yaml') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $repo 'automation/start.ps1') -PathType Leaf)) {
    throw 'No se encontro una raiz valida de SmartIR-Net. No se borro nada.'
}

# Elementos generados, no configuraciones ni registros operativos.
$relative = @(
    '.test-runs',
    '.pytest_cache',
    '.lab-runtime',
    'frontend/dist',
    'frontend/node_modules',
    'frontend/test-results',
    'frontend/playwright-report',
    'automation/supervise.ps1.bak',
    'automation/supervise.ps1.respaldo'
)
$deleted = 0
foreach ($item in $relative) {
    $path = Join-Path $repo $item
    if (Test-Path -LiteralPath $path) {
        if ($PSCmdlet.ShouldProcess($path, 'Eliminar temporal')) {
            Remove-Item -LiteralPath $path -Recurse -Force
            $deleted++
        }
    }
}

# Cachés Python; nunca explorar el entorno virtual.
foreach ($rootName in @('backend/app', 'agent/smartir_agent', 'tools', 'automation')) {
    $path = Join-Path $repo $rootName
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { continue }
    Get-ChildItem -LiteralPath $path -Directory -Filter '__pycache__' -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
        if ($PSCmdlet.ShouldProcess($_.FullName, 'Eliminar cache Python')) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
            $deleted++
        }
    }
}
Write-Output "Limpieza local terminada. Elementos eliminados: $deleted."
Write-Output 'Intactos: .git, .env, .venv, lab.local.json, Docker, WSL y archivos EVE/estado.'
