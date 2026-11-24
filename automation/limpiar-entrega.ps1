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
$failed = New-Object 'System.Collections.Generic.List[string]'
foreach ($item in $relative) {
    $path = Join-Path $repo $item
    if (Test-Path -LiteralPath $path) {
        if ($PSCmdlet.ShouldProcess($path, 'Eliminar temporal')) {
            try {
                Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
                $deleted++
            } catch {
                # Un directorio protegido o un archivo en uso no debe bloquear
                # el resto de la limpieza. No elevar privilegios ni modificar ACL.
                $failed.Add($item)
                Write-Warning "No se pudo eliminar '$item'. La limpieza continuara con el resto."
            }
        }
    }
}

# Cachés Python; nunca explorar el entorno virtual.
foreach ($rootName in @('backend/app', 'agent/smartir_agent', 'tools', 'automation')) {
    $path = Join-Path $repo $rootName
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { continue }
    Get-ChildItem -LiteralPath $path -Directory -Filter '__pycache__' -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
        if ($PSCmdlet.ShouldProcess($_.FullName, 'Eliminar cache Python')) {
            try {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
                $deleted++
            } catch {
                $failed.Add($_.FullName.Substring($repo.Length).TrimStart([char]'\'))
                Write-Warning 'No se pudo eliminar una cache Python; se conserva para revision.'
            }
        }
    }
}
Write-Output "Limpieza local terminada. Elementos eliminados: $deleted."
if ($failed.Count -gt 0) {
    Write-Warning ("Limpieza parcial: {0} elemento(s) sin eliminar: {1}" -f $failed.Count, ($failed -join ', '))
    Write-Output 'Estos temporales no se incluyen en git archive y no impiden crear el ZIP de entrega.'
} else {
    Write-Output 'Todos los elementos temporales encontrados se eliminaron.'
}
Write-Output 'Intactos: .git, .env, .venv, lab.local.json, Docker, WSL y archivos EVE/estado.'
