# Essai de l'étude n°17. Ne fait partie ni de l'application ni du paquet livré.
# Mesure, sur cette machine : taille du dossier portable, puis images/s de
# QTGMC (qtgmc.vpy du logiciel) et de bwdif (FFmpeg 9.1 du logiciel).
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Result([string]$key, [string]$value) {
    Write-Output "RESULTAT $key=$value"
}

function Format-Mo([int64]$octets) {
    return ("{0:N2} Mo ({1} octets)" -f ($octets / 1MB), $octets)
}

Write-Output "=== MACHINE ==="
Write-Result "OS" $env:OS
Write-Result "IMAGE_OS" "$env:ImageOS"
Write-Result "IMAGE_VERSION" "$env:ImageVersion"
Write-Result "PROCESSEURS_ENV" "$env:NUMBER_OF_PROCESSORS"
Get-CimInstance Win32_Processor | ForEach-Object {
    Write-Result "CPU" "$($_.Name) coeurs=$($_.NumberOfCores) logiques=$($_.NumberOfLogicalProcessors)"
}
$ram = [int64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
Write-Result "RAM_OCTETS" "$ram"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptVs = Join-Path $repo "vhs-restore-ai\vhs_restore\qtgmc.vpy"
$requirements = Join-Path $repo "vhs-restore-ai\requirements-qtgmc.txt"
if (-not (Test-Path $scriptVs)) { throw "Script introuvable : $scriptVs" }

$ffmpeg = Join-Path $env:RUNNER_TEMP "vhs-tools\ffmpeg\bin\ffmpeg.exe"
$ffprobe = Join-Path $env:RUNNER_TEMP "vhs-tools\ffmpeg\bin\ffprobe.exe"
if (-not (Test-Path $ffmpeg)) { throw "FFmpeg introuvable : $ffmpeg" }
Write-Result "FFMPEG" (& $ffmpeg -hide_banner -version | Select-Object -First 1)

$msvcp = Get-Command MSVCP140.dll -ErrorAction SilentlyContinue
if (-not $msvcp) {
    $candidats = @(
        "$env:SystemRoot\System32\MSVCP140.dll",
        "$env:SystemRoot\System32\msvcp140.dll"
    )
    $msvcpPath = $candidats | Where-Object { Test-Path $_ } | Select-Object -First 1
} else {
    $msvcpPath = $msvcp.Source
}
if ($msvcpPath) {
    Write-Result "MSVCP140" "$msvcpPath taille=$((Get-Item $msvcpPath).Length)"
} else {
    Write-Result "MSVCP140" "introuvable"
}

Write-Output "=== PYTHON EMBARQUE ==="
$pyver = "3.13.12"
$travail = Join-Path $env:RUNNER_TEMP "qtgmc-etude"
if (Test-Path $travail) { Remove-Item -Recurse -Force $travail }
New-Item -ItemType Directory -Force -Path $travail | Out-Null
$portable = Join-Path $travail "portable"
$zipPy = Join-Path $travail "python-$pyver-embed-amd64.zip"
$pyUrl = "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip"
Write-Output "Telechargement $pyUrl"
Invoke-WebRequest -Uri $pyUrl -OutFile $zipPy
Write-Result "PYTHON_EMBED_ZIP_OCTETS" "$((Get-Item $zipPy).Length)"
Expand-Archive -LiteralPath $zipPy -DestinationPath $portable -Force
$pth = Join-Path $portable "python313._pth"
$lignes = Get-Content $pth
$lignes = $lignes | ForEach-Object { if ($_ -eq "#import site" -or $_ -eq "# import site") { "import site" } else { $_ } }
if ($lignes -notcontains "Lib\site-packages") { $lignes += "Lib\site-packages" }
if ($lignes -notcontains "import site") { $lignes += "import site" }
Set-Content -Path $pth -Value $lignes -Encoding ascii
Write-Output "python313._pth :"
Get-Content $pth | ForEach-Object { Write-Output "  $_" }

$getPip = Join-Path $travail "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
$python = Join-Path $portable "python.exe"
$env:PYTHONDONTWRITEBYTECODE = "1"
& $python $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip a échoué ($LASTEXITCODE)" }
& $python -m pip install --disable-pip-version-check --no-warn-script-location -r $requirements
if ($LASTEXITCODE -ne 0) { throw "pip install a échoué ($LASTEXITCODE)" }

function Measure-Tree([string]$path) {
    $somme = [int64]0
    Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $somme += $_.Length }
    return $somme
}

Write-Result "PORTABLE_AVEC_PIP_OCTETS" "$(Measure-Tree $portable)"
Get-ChildItem -LiteralPath $portable -Recurse -Filter *.pdb -File | Remove-Item -Force
$pipDirs = @(
    (Join-Path $portable "Lib\site-packages\pip"),
    (Join-Path $portable "Lib\site-packages\setuptools"),
    (Join-Path $portable "Lib\site-packages\pkg_resources"),
    (Join-Path $portable "Lib\site-packages\_distutils_hack"),
    (Join-Path $portable "Lib\site-packages\wheel")
)
foreach ($d in $pipDirs) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
Get-ChildItem -LiteralPath (Join-Path $portable "Lib\site-packages") -Filter "pip-*.dist-info" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $portable "Lib\site-packages") -Filter "setuptools-*.dist-info" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $portable "Lib\site-packages") -Filter "wheel-*.dist-info" -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
$sansPip = Measure-Tree $portable
Write-Result "PORTABLE_SANS_PDB_SANS_PIP_OCTETS" "$sansPip"
Write-Result "PORTABLE_SANS_PDB_SANS_PIP_MO" ("{0:N2}" -f ($sansPip / 1MB))

Write-Output "=== TAILLE PAR DOSSIER DE SITE-PACKAGES ==="
$site = Join-Path $portable "Lib\site-packages"
Get-ChildItem -LiteralPath $site -Force | ForEach-Object {
    if ($_.PSIsContainer) {
        $n = Measure-Tree $_.FullName
        Write-Result ("DOSSIER_" + $_.Name) "$n"
    } else {
        Write-Result ("FICHIER_" + $_.Name) "$($_.Length)"
    }
}

$zipBundle = Join-Path $travail "portable-sans-pdb.zip"
if (Test-Path $zipBundle) { Remove-Item -Force $zipBundle }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($portable, $zipBundle, [System.IO.Compression.CompressionLevel]::Optimal, $false)
Write-Result "PORTABLE_ZIP_OCTETS" "$((Get-Item $zipBundle).Length)"
Write-Result "PORTABLE_ZIP_MO" ("{0:N2}" -f ((Get-Item $zipBundle).Length / 1MB))

$vspipe = Join-Path $site "vapoursynth\vspipe.exe"
if (-not (Test-Path $vspipe)) {
    $trouve = Get-ChildItem -LiteralPath $portable -Recurse -Filter vspipe.exe | Select-Object -First 1
    if (-not $trouve) { throw "vspipe.exe introuvable dans le dossier portable" }
    $vspipe = $trouve.FullName
}
Write-Result "VSPIPE" $vspipe
$env:PATH = "$portable;$site\vapoursynth;" + $env:PATH

Write-Output "=== VERSION ==="
& $vspipe --version
Write-Output "=== PLUGINS CHARGES AU DEMARRAGE ==="
& $python -c "import vapoursynth as vs; print(vs.core); print('ESPACES ' + ' '.join(sorted(p.namespace for p in vs.core.plugins())))"

Write-Output "=== SOURCE 720x576 ==="
$src = Join-Path $travail "source.mkv"
& $ffmpeg -y -hide_banner -loglevel error -f lavfi -i "testsrc2=size=720x576:rate=50:duration=15" -vf "format=yuv420p,tinterlace=mode=interleave_top,setfield=tff" -flags +ildct+ilme -r 25 -c:v ffv1 -an $src
if ($LASTEXITCODE -ne 0) { throw "Génération de la source échouée ($LASTEXITCODE)" }
$probe = & $ffprobe -v error -select_streams v:0 -show_entries stream=width,height,field_order,avg_frame_rate,nb_frames,codec_name -of json $src
Write-Output $probe
$info = $probe | ConvertFrom-Json
$flux = $info.streams[0]
Write-Result "SOURCE_LARGEUR" "$($flux.width)"
Write-Result "SOURCE_HAUTEUR" "$($flux.height)"
Write-Result "SOURCE_BALAYAGE" "$($flux.field_order)"
Write-Result "SOURCE_CADENCE" "$($flux.avg_frame_rate)"
Write-Result "SOURCE_IMAGES" "$($flux.nb_frames)"
Write-Result "SOURCE_CODEC" "$($flux.codec_name)"
Write-Result "SOURCE_OCTETS" "$((Get-Item $src).Length)"
if ([int]$flux.width -ne 720 -or [int]$flux.height -ne 576) { throw "La source n'est pas en 720×576" }

function Invoke-Chrono([string]$nom, [string]$ligne) {
    $journal = Join-Path $travail "$nom.txt"
    $bat = Join-Path $travail "$nom.cmd"
    if (Test-Path $journal) { Remove-Item -Force $journal }
    # Fichier .cmd : évite que PowerShell avale le y4m et fausse le chrono.
    Set-Content -LiteralPath $bat -Encoding ascii -Value "@echo off`r`n$ligne > NUL 2> `"$journal`"`r`n"
    Write-Output "BEGIN $nom"
    Write-Output (Get-Content -LiteralPath $bat -Raw)
    $chrono = [Diagnostics.Stopwatch]::StartNew()
    cmd.exe /d /c $bat
    $code = $LASTEXITCODE
    $chrono.Stop()
    $secondes = $chrono.Elapsed.TotalSeconds
    $texteSec = $secondes.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture)
    Write-Output "END $nom exit=$code secondes=$texteSec"
    Write-Result "${nom}_EXIT" "$code"
    Write-Result "${nom}_SECONDES" $texteSec
    Write-Output "----- journal $nom -----"
    if (Test-Path $journal) { Get-Content -LiteralPath $journal -Tail 40 }
    $script:dernierCode = $code
    $script:dernieresSecondes = $secondes
}

function Lire-Journal([string]$nom) {
    $journal = Join-Path $travail "$nom.txt"
    if (-not (Test-Path $journal)) { return "" }
    return [IO.File]::ReadAllText($journal)
}

function Ecrire-FpsMur([string]$nom, [double]$secondes, [int]$images) {
    if ($images -gt 0 -and $secondes -gt 0) {
        $fps = $images / $secondes
        Write-Result "${nom}_FPS_MUR" ($fps.ToString("0.00", [Globalization.CultureInfo]::InvariantCulture))
        Write-Result "${nom}_IMAGES" "$images"
    }
}

Write-Output "=== ESSAI A BLANC (check=1) ==="
Invoke-Chrono "CHECK" "`"$vspipe`" -a check=1 -e 1 `"$scriptVs`" -"
if ($script:dernierCode -ne 0) { throw "L'essai à blanc de qtgmc.vpy a échoué ($($script:dernierCode))" }

Write-Output "=== QTGMC PUIS BWDIF ==="
# Première passe : indexation BestSource comprise. Deuxième : cache déjà écrit.
# Le mur est le même procédé pour les deux outils : images de sortie / secondes.
Invoke-Chrono "QTGMC_1" "`"$vspipe`" -p -c y4m -a src=$src -a tff=1 -a first=0 -a count=0 `"$scriptVs`" -"
$codeQ1 = $script:dernierCode
$secQ1 = $script:dernieresSecondes
if ($codeQ1 -eq 0) {
    Invoke-Chrono "QTGMC_2" "`"$vspipe`" -p -c y4m -a src=$src -a tff=1 -a first=0 -a count=0 `"$scriptVs`" -"
    $codeQ2 = $script:dernierCode
    $secQ2 = $script:dernieresSecondes
} else {
    Write-Result "QTGMC_2_EXIT" "non_lance"
    $codeQ2 = $codeQ1
    $secQ2 = 0
}
$filtre = "bwdif=mode=send_field:parity=tff:deint=all"
Invoke-Chrono "BWDIF_1" "`"$ffmpeg`" -hide_banner -stats -i `"$src`" -vf $filtre -f null -"
$codeB1 = $script:dernierCode
$secB1 = $script:dernieresSecondes
Invoke-Chrono "BWDIF_2" "`"$ffmpeg`" -hide_banner -stats -i `"$src`" -vf $filtre -f null -"
$codeB2 = $script:dernierCode
$secB2 = $script:dernieresSecondes

$texteQ = Lire-Journal $(if ($codeQ1 -eq 0) { "QTGMC_2" } else { "QTGMC_1" })
$q = [regex]::Match($texteQ, "Output\s+(\d+)\s+frames in\s+([0-9.]+)\s+seconds\s+\(([0-9.]+)\s+fps\)")
if ($q.Success) {
    Write-Result "QTGMC_IMAGES_SORTIE" $q.Groups[1].Value
    Write-Result "QTGMC_SECONDES_OUTIL" $q.Groups[2].Value
    Write-Result "QTGMC_FPS_OUTIL" $q.Groups[3].Value
    Ecrire-FpsMur "QTGMC_2" $secQ2 ([int]$q.Groups[1].Value)
    $q1texte = Lire-Journal "QTGMC_1"
    $q1m = [regex]::Match($q1texte, "Output\s+(\d+)\s+frames in\s+([0-9.]+)\s+seconds\s+\(([0-9.]+)\s+fps\)")
    if ($q1m.Success) {
        Write-Result "QTGMC_1_FPS_OUTIL" $q1m.Groups[3].Value
        Ecrire-FpsMur "QTGMC_1" $secQ1 ([int]$q1m.Groups[1].Value)
    }
} else {
    Write-Result "QTGMC_FPS_OUTIL" "illisible"
}

function Dernier-Nombre([string]$texte, [string]$motif) {
    $tous = [regex]::Matches($texte, $motif)
    if ($tous.Count -eq 0) { return $null }
    return [int]$tous[$tous.Count - 1].Groups[1].Value
}

$texteB = Lire-Journal "BWDIF_2"
$imagesB = Dernier-Nombre $texteB "frame=\s*(\d+)"
if ($imagesB) {
    Write-Result "BWDIF_IMAGES_SORTIE" "$imagesB"
    Ecrire-FpsMur "BWDIF_2" $secB2 $imagesB
    $imagesB1 = Dernier-Nombre (Lire-Journal "BWDIF_1") "frame=\s*(\d+)"
    if ($imagesB1) { Ecrire-FpsMur "BWDIF_1" $secB1 $imagesB1 }
} else {
    Write-Result "BWDIF_FPS_FFMPEG" "illisible"
}

Get-ChildItem -LiteralPath $travail -File | Where-Object { $_.Extension -match "\.(lwi|json|bin)$" -or $_.Name -like "*index*" } | ForEach-Object {
    Write-Result ("INDEX_" + $_.Name) "$($_.Length)"
}
Get-ChildItem -LiteralPath $travail -Recurse -File -Force | Where-Object { $_.Name -match "index|bsindex|\.lwi" } | ForEach-Object {
    Write-Result ("INDEX_" + $_.Name) "$($_.Length)"
}

if ($codeQ2 -ne 0) { throw "QTGMC a échoué (code $codeQ2)" }
if ($codeB2 -ne 0) { throw "bwdif a échoué (code $codeB2)" }
Write-Output "=== FIN ESSAI ==="
