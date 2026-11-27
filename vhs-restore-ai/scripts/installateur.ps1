# Fabrique le programme d'installation (Inno Setup) à partir de dist\VHSRestoreAI.
# Utilisé par fabriquer_exe.ps1 et par la fabrication GitHub. Inno Setup est installé au besoin
# (version figée, empreinte SHA-256 vérifiée), dans le profil, sans droits d'administrateur.
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Nom
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'      # la barre de PowerShell 5.1 ralentit beaucoup le téléchargement
$racine = Split-Path -Parent $PSScriptRoot           # dossier vhs-restore-ai
# relevée le 27 novembre 2026 sur le fichier publié
$innoUrl = 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe'
$innoSha = 'A549929319F9120716677C685535CA4671E4B937B5FDC87E2585F32D8EB30E8C'

function TrouverIscc {
    $candidats = @()
    if ($env:LOCALAPPDATA) { $candidats += Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe' }
    if (${env:ProgramFiles(x86)}) { $candidats += Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
    if ($env:ProgramFiles) { $candidats += Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe' }
    foreach ($c in $candidats) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$iscc = TrouverIscc
if (-not $iscc) {
    Write-Host "Installation d'Inno Setup 6.7.4 (pour fabriquer le programme d'installation)..."
    $fichier = Join-Path $env:TEMP 'innosetup-6.7.4.exe'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $innoUrl -OutFile $fichier -UseBasicParsing
    $h = (Get-FileHash $fichier -Algorithm SHA256).Hash
    if ($h -ne $innoSha) {
        Remove-Item $fichier -Force -ErrorAction SilentlyContinue
        throw "Inno Setup téléchargé : empreinte différente ($h). Rien n'a été installé."
    }
    $p = Start-Process -FilePath $fichier -Wait -PassThru `
        -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER'
    Remove-Item $fichier -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) { throw "L'installation d'Inno Setup a échoué (code $($p.ExitCode))." }
    $iscc = TrouverIscc
    if (-not $iscc) { throw "Inno Setup est installé, mais ISCC.exe est introuvable." }
}

$source = Join-Path $racine 'dist\VHSRestoreAI'
if (-not (Test-Path (Join-Path $source 'VHSRestoreAI.exe'))) { throw "dist\VHSRestoreAI\VHSRestoreAI.exe introuvable : fabriquez l'exe d'abord." }
$sortie = Join-Path $racine 'livraison'
New-Item -ItemType Directory -Force $sortie | Out-Null
$icone = Join-Path $racine 'vhs_restore\assets\VHSRestoreAI.ico'
$script = Join-Path $racine 'installateur\VHSRestoreAI.iss'
& $iscc /Q "/DVersion=$Version" "/DSource=$source" "/DSortie=$sortie" "/DNomSortie=$Nom" "/DIcone=$icone" $script
if ($LASTEXITCODE -ne 0) { throw "La fabrication du programme d'installation a échoué (code $LASTEXITCODE)." }
$setup = Join-Path $sortie "$Nom.exe"
if (-not (Test-Path $setup)) { throw "Programme d'installation introuvable : $setup" }
$sha = (Get-FileHash $setup -Algorithm SHA256).Hash
"$sha  $Nom.exe" | Set-Content (Join-Path $sortie "$Nom.sha256") -Encoding Ascii
Write-Host "Programme d'installation : $setup"
