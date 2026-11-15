# Télécharge les outils externes dans le dossier tools\ de l'application.
#   FFmpeg (obligatoire)   : build "release essentials" de gyan.dev, somme SHA-256 vérifiée.
#   Real-ESRGAN (option)   : -AvecIA, exécutable ncnn-vulkan officiel v0.2.5.0 (GPU Vulkan requis).
#   DeepFilterNet (option) : -AvecSon, binaire officiel v0.5.6 (voix, plafond 12 dB dans l'application).
#   (-AvecQTGMC est traité par installer.bat : paquets pip dans .venv)
param([switch]$AvecIA, [switch]$AvecQTGMC, [switch]$AvecPoussieres, [switch]$AvecSon)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root  = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root 'tools'
New-Item -ItemType Directory -Force $tools | Out-Null

function Install-Zip($url, $dest, $exeName, $sha256Url) {
    $zip = Join-Path $env:TEMP ("vhsra_" + [IO.Path]::GetFileName($url))
    $tmp = Join-Path $env:TEMP ("vhsra_x_" + [guid]::NewGuid())
    Write-Host "Téléchargement de $url ..."
    # 3 tentatives : un site momentanément indisponible (erreur 503) ne doit pas tout arrêter.
    for ($essai = 1; $essai -le 3; $essai++) {
        try { Invoke-WebRequest $url -OutFile $zip -UseBasicParsing; break }
        catch {
            if ($essai -eq 3) { throw "Téléchargement impossible de $url après 3 essais : $($_.Exception.Message)" }
            Write-Host "Site indisponible (essai $essai sur 3), nouvel essai dans $(30 * $essai) s..."
            Start-Sleep -Seconds (30 * $essai)
        }
    }
    if ($sha256Url) {
        $page = $null
        for ($essai = 1; $essai -le 3 -and -not $page; $essai++) {
            try { $page = Invoke-WebRequest $sha256Url -UseBasicParsing }
            catch { if ($essai -eq 3) { throw } ; Start-Sleep -Seconds (30 * $essai) }
        }
        $expected = ($page.Content.ToString().Trim() -split '\s+')[0]
        $actual = (Get-FileHash $zip -Algorithm SHA256).Hash
        if ($actual -ne $expected.ToUpper()) { throw "Somme SHA-256 incorrecte pour $url" }
        Write-Host "Somme SHA-256 vérifiée."
    }
    Expand-Archive $zip $tmp -Force
    $exe = Get-ChildItem $tmp -Recurse -Filter $exeName | Select-Object -First 1
    if (-not $exe) { throw "$exeName introuvable dans l'archive" }
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    $src = $exe.Directory.FullName
    if ($exe.Directory.Name -eq 'bin') { $src = $exe.Directory.Parent.FullName }
    Move-Item $src $dest
    Remove-Item -Recurse -Force $zip, $tmp -ErrorAction SilentlyContinue
}

$ff = Join-Path $tools 'ffmpeg'
if (Test-Path (Join-Path $ff 'bin\ffmpeg.exe')) {
    Write-Host "FFmpeg déjà présent."
} else {
    $u = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    Install-Zip $u $ff 'ffmpeg.exe' "$u.sha256"
}
& (Join-Path $ff 'bin\ffmpeg.exe') -hide_banner -version | Select-Object -First 1

if ($AvecIA) {
    $re = Join-Path $tools 'realesrgan'
    if (Test-Path (Join-Path $re 'realesrgan-ncnn-vulkan.exe')) {
        Write-Host "Real-ESRGAN déjà présent."
    } else {
        Install-Zip 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip' `
            $re 'realesrgan-ncnn-vulkan.exe' $null
    }
}
if ($AvecSon) {
    $dir = Join-Path $tools 'deepfilter'
    $exe = Join-Path $dir 'deep-filter.exe'
    if (Test-Path $exe) {
        Write-Host "DeepFilterNet déjà présent."
    } else {
        New-Item -ItemType Directory -Force $dir | Out-Null
        $url = 'https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-pc-windows-msvc.exe'
        Write-Host "Téléchargement de DeepFilterNet ..."
        Invoke-WebRequest $url -OutFile $exe -UseBasicParsing
        Write-Host "DeepFilterNet installé : $exe"
    }
}
Write-Host "Outils installés dans $tools"
