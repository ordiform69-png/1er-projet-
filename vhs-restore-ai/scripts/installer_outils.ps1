# Les versions, empreintes et opérations de publication sont communes avec l’application.
param([switch]$AvecIA, [switch]$AvecQTGMC, [switch]$AvecPoussieres, [switch]$AvecSon,
      [switch]$AvecCouleurs, [string]$Dossier = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Dossier) { $Dossier = Join-Path $root 'tools' }
$dest = [IO.Path]::GetFullPath($Dossier)
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$cles = @('ffmpeg')
if ($AvecIA) { $cles += 'realesrgan' }
if ($AvecSon) { $cles += 'deepfilter' }
if ($AvecCouleurs) { $cles += 'colorisation' }
Push-Location $root
try {
    & $python -m vhs_restore.installer $dest @cles
    if ($LASTEXITCODE -ne 0) { throw "L’installation des outils a échoué." }
} finally {
    Pop-Location
}
