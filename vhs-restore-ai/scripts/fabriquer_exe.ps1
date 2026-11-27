# Fabrique l'exe de VHS Restore AI sur ce PC Windows, comme la fabrication GitHub
# (.github/workflows/vhs-restore-windows.yml), mais avec une courte sélection de tests au lieu
# de la suite complète (1 h 30). Lancement : fabriquer_exe.bat (double-clic).
#   -SansTests      : aucune vérification avant (le plus rapide, pour un essai)
#   -TousLesTests   : la suite complète, comme sur GitHub
#   -SansMiseAJour  : ne pas récupérer la dernière version du projet (git pull)
param([switch]$SansTests, [switch]$TousLesTests, [switch]$SansMiseAJour)
$ErrorActionPreference = 'Stop'
$racine = Split-Path -Parent $PSScriptRoot          # dossier vhs-restore-ai
Set-Location $racine
$debut = Get-Date

function Etape([string]$texte) {
    Write-Host ''
    Write-Host "== $texte" -ForegroundColor Cyan
}
function Verifier([string]$quoi) {
    if ($LASTEXITCODE -ne 0) { throw "$quoi a échoué (code $LASTEXITCODE)." }
}

if (-not $SansMiseAJour -and (Get-Command git -ErrorAction SilentlyContinue)) {
    Etape 'Mise à jour du projet'
    git -C $racine pull --ff-only
    Verifier 'La mise à jour (git pull)'
}

Etape 'Python et ses modules'
$venv = Join-Path $racine '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv $venv } else { & python -m venv $venv }
    Verifier "La création de l'environnement Python (Python 3.10 ou plus récent est-il installé ?)"
}
& $python -m pip install --disable-pip-version-check -q --upgrade pip
Verifier 'La mise à jour de pip'
& $python -m pip install --disable-pip-version-check -q -r requirements-dev.txt -r requirements-poussieres.txt -r requirements-couleurs.txt pyinstaller==6.22.3
Verifier "L'installation des modules Python"

Etape 'FFmpeg et modèle de colorisation'
& (Join-Path $PSScriptRoot 'installer_outils.ps1') -AvecCouleurs

$cheminAvant = $env:PATH
$env:PATH = "$racine\tools\ffmpeg\bin;$env:PATH"
$env:VHSRA_DDCOLOR = "$racine\tools\ddcolor\ddcolor-tiny-fp16.onnx"
if (-not $SansTests) {
    Etape 'Vérifications avant fabrication'
    if ($TousLesTests) {
        $cibles = @('tests')
    } else {
        $cibles = @('tests/test_aac_ffmpeg9.py', 'tests/test_pipeline.py', 'tests/test_scenes.py',
                    'tests/test_reprise.py', 'tests/test_copie_lecture.py', 'tests/test_lumiere.py',
                    'tests/test_estimation.py', 'tests/test_ecrans.py')
    }
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:PYTHONUTF8 = '1'
    & $python -m pytest -q -rfE @cibles -o faulthandler_timeout=900
    $resultat = $LASTEXITCODE
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    if ($resultat -ne 0) { throw "Des vérifications ont échoué : l'exe n'est pas fabriqué." }
}

Etape "Fabrication de l'application"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $python -m PyInstaller --noconfirm VHSRestoreAI.spec
Verifier 'PyInstaller'

Etape 'Ajout de FFmpeg, du mode d''emploi et des licences'
New-Item -ItemType Directory -Force dist\VHSRestoreAI\tools\ffmpeg\bin | Out-Null
Copy-Item tools\ffmpeg\bin\ffmpeg.exe, tools\ffmpeg\bin\ffprobe.exe dist\VHSRestoreAI\tools\ffmpeg\bin\
Copy-Item tools\ffmpeg\LICENSE* dist\VHSRestoreAI\tools\ffmpeg\ -ErrorAction SilentlyContinue
Copy-Item LISEZMOI.txt dist\VHSRestoreAI\
New-Item -ItemType Directory -Force dist\VHSRestoreAI\licences | Out-Null
New-Item -ItemType Directory -Force dist\VHSRestoreAI\tools\ddcolor | Out-Null
Copy-Item tools\ddcolor\ddcolor-tiny-fp16.onnx dist\VHSRestoreAI\tools\ddcolor\
Copy-Item vhs_restore\models\DDCOLOR-LICENSE.txt dist\VHSRestoreAI\licences\
& $python -c "import importlib.metadata as m; d=m.distribution('analog-repair'); f=[p for p in d.files if 'LICENSE' in p.name.upper()]; open('dist/VHSRestoreAI/licences/analog-repair-LICENSE.txt','w',encoding='utf-8').write(f[0].read_text(encoding='utf-8') if f else 'MIT - https://github.com/Bratwurstexe/ANALOG_REPAIR')"
Verifier 'La copie des licences'

Etape "Essai de l'exe fabriqué (sans le Python ni le FFmpeg du PC)"
$dossierEssai = Join-Path $env:TEMP 'autotest vhs été'
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
function EssaiExe([string]$option, [string]$fichier) {
    $p = Start-Process -FilePath (Join-Path $racine 'dist\VHSRestoreAI\VHSRestoreAI.exe') `
        -ArgumentList $option, "`"$dossierEssai`"" -Wait -PassThru
    Get-Content (Join-Path $dossierEssai $fichier) -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) { $env:PATH = $cheminAvant; throw "L'essai $option a échoué (code $($p.ExitCode))." }
}
EssaiExe '--autotest' 'autotest.txt'
EssaiExe '--autotest-lecteur' 'autotest-lecteur.txt'
$env:PATH = $cheminAvant

Etape 'Paquet'
$commit = 'local'
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        $c = git -C $racine rev-parse --short HEAD
        if ($LASTEXITCODE -eq 0 -and $c) { $commit = "$c".Trim() }
    } catch { $commit = 'local' }
}
$nom = "VHSRestoreAI-Windows-local-$(Get-Date -Format 'yyyyMMdd-HHmm')-$commit"
New-Item -ItemType Directory -Force livraison | Out-Null
Compress-Archive -Path dist\VHSRestoreAI -DestinationPath "livraison\$nom.zip" -Force
$empreinte = (Get-FileHash "livraison\$nom.zip" -Algorithm SHA256).Hash
"$empreinte  $nom.zip" | Set-Content "livraison\$nom.sha256" -Encoding Ascii

Etape "Programme d'installation (icône « VHS Restore AI » sur le bureau)"
$setup = "Installer-VHS-Restore-AI-local-$(Get-Date -Format 'yyyyMMdd-HHmm')-$commit"
try {
    & (Join-Path $PSScriptRoot 'installateur.ps1') -Version (Get-Date -Format 'yyyy.M.d.Hmm') -Nom $setup
} catch {
    # le zip est prêt quoi qu'il arrive : un échec ici ne le perd pas
    Write-Warning "Programme d'installation non fabriqué : $($_.Exception.Message) Le zip, lui, est prêt."
}
$minutes = [math]::Round(((Get-Date) - $debut).TotalMinutes, 1)
Write-Host ''
Write-Host "Prêt en $minutes min : livraison\$nom.zip" -ForegroundColor Green
if (Test-Path "livraison\$setup.exe") {
    Write-Host "Pour installer avec une icône sur le bureau : livraison\$setup.exe" -ForegroundColor Green
}
Start-Process explorer.exe (Resolve-Path livraison).Path
