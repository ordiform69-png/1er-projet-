# Étude n°13 étape 2. Ne fait partie ni de l'application ni du paquet livré.
# 1. Deux fabrications du dossier dist/VHSRestoreAI, avec les mêmes commandes
#    que .github/workflows/vhs-restore-windows.yml (PyInstaller, copies, zip).
#    Avant : le spec plus l'exclusion de Qt Multimedia (le paquet sans ces modules).
#    Après : le spec du dépôt, tel que la fabrication Windows le lance.
# 2. Mire entrelacée lue par le widget Lecteur, et écarts de lignes.
# Les tests pytest et l'autotest ne changent pas les octets du paquet : ils ne sont pas relancés.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Result([string]$key, [string]$value) {
    # Write-Host : sinon la ligne partirait dans la valeur de retour des fonctions.
    $ligne = "RESULTAT $key=$value"
    Write-Host $ligne
    Add-Content -LiteralPath $script:Mesures -Value $ligne -Encoding utf8
}

if (-not $env:RUNNER_TEMP) { $env:RUNNER_TEMP = [IO.Path]::GetTempPath() }
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location (Join-Path $repo "vhs-restore-ai")

$sortie = Join-Path $repo "vhs-restore-ai\partage-grok\etude-lecteur-n13"
if (Test-Path $sortie) { Remove-Item -Recurse -Force $sortie }
New-Item -ItemType Directory -Force -Path $sortie | Out-Null
$script:Mesures = Join-Path $sortie "mesures.txt"
"" | Set-Content -LiteralPath $script:Mesures -Encoding utf8

Write-Output "=== MACHINE ==="
Write-Result "COMMIT" (git rev-parse HEAD)
Write-Result "OS" "$env:OS"
Write-Result "IMAGE_OS" "$env:ImageOS"
Write-Result "IMAGE_VERSION" "$env:ImageVersion"
Write-Result "PROCESSEURS" "$env:NUMBER_OF_PROCESSORS"
Get-CimInstance Win32_Processor | ForEach-Object {
    Write-Result "CPU" "$($_.Name) coeurs=$($_.NumberOfCores) logiques=$($_.NumberOfLogicalProcessors)"
}
$ram = [int64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
Write-Result "RAM_OCTETS" "$ram"
Write-Result "PYTHON" (python -c "import sys; print(sys.version.split()[0])")
Write-Result "PYSIDE" (python -c "import PySide6; print(PySide6.__version__)")
Write-Result "PYINSTALLER" (python -c "import PyInstaller; print(PyInstaller.__version__)")
Write-Result "NUMPY" (python -c "import numpy; print(numpy.__version__)")

function Measure-Tree([string]$path) {
    # foreach (et non ForEach-Object) : l'addition resterait sinon dans un autre scope.
    $somme = [int64]0
    $n = 0
    foreach ($fichier in (Get-ChildItem -LiteralPath $path -Recurse -File -Force)) {
        $somme += $fichier.Length
        $n += 1
    }
    return @{ Octets = $somme; Fichiers = $n }
}

function Get-Inventory([string]$path) {
    $root = (Resolve-Path -LiteralPath $path).Path
    $map = [ordered]@{}
    foreach ($fichier in (Get-ChildItem -LiteralPath $path -Recurse -File -Force)) {
        $rel = $fichier.FullName.Substring($root.Length).TrimStart('\', '/') -replace '\\', '/'
        $map[$rel] = [int64]$fichier.Length
    }
    return $map
}

function Completer-Paquet {
    # Mêmes copies que vhs-restore-windows.yml, après pyinstaller.
    New-Item -ItemType Directory -Force dist/VHSRestoreAI/tools/ffmpeg/bin | Out-Null
    Copy-Item tools/ffmpeg/bin/ffmpeg.exe, tools/ffmpeg/bin/ffprobe.exe dist/VHSRestoreAI/tools/ffmpeg/bin/
    Copy-Item tools/ffmpeg/LICENSE* dist/VHSRestoreAI/tools/ffmpeg/ -ErrorAction SilentlyContinue
    Copy-Item LISEZMOI.txt dist/VHSRestoreAI/
    New-Item -ItemType Directory -Force dist/VHSRestoreAI/licences | Out-Null
    New-Item -ItemType Directory -Force dist/VHSRestoreAI/tools/ddcolor | Out-Null
    Copy-Item tools/ddcolor/ddcolor-tiny-fp16.onnx dist/VHSRestoreAI/tools/ddcolor/
    Copy-Item vhs_restore/models/DDCOLOR-LICENSE.txt dist/VHSRestoreAI/licences/
    python -c "import importlib.metadata as m; d=m.distribution('analog-repair'); f=[p for p in d.files if 'LICENSE' in p.name.upper()]; open('dist/VHSRestoreAI/licences/analog-repair-LICENSE.txt','w',encoding='utf-8').write(f[0].read_text(encoding='utf-8') if f else 'MIT - https://github.com/Bratwurstexe/ANALOG_REPAIR')"
}

function Invoke-Paquet([string]$etiquette) {
    if (Test-Path dist) { Remove-Item -Recurse -Force dist }
    if (Test-Path build) { Remove-Item -Recurse -Force build }
    $journal = Join-Path $env:RUNNER_TEMP "pyinstaller-$etiquette.log"
    Write-Host "BEGIN PYINSTALLER $etiquette"
    # Même commande que vhs-restore-windows.yml. Le journal est à part pour garder les RESULTAT lisibles.
    & pyinstaller --noconfirm VHSRestoreAI.spec *> $journal
    $code = $LASTEXITCODE
    Write-Host "END PYINSTALLER $etiquette exit=$code"
    if ($code -ne 0) {
        Get-Content -LiteralPath $journal -Tail 60 | Write-Host
        throw "pyinstaller $etiquette a échoué ($code)"
    }
    Completer-Paquet
    $arbre = Measure-Tree "dist\VHSRestoreAI"
    $mo = ($arbre.Octets / 1MB).ToString("0.00", [Globalization.CultureInfo]::InvariantCulture)
    Write-Result "${etiquette}_DECOMPRESSE_OCTETS" "$($arbre.Octets)"
    Write-Result "${etiquette}_DECOMPRESSE_MO" $mo
    Write-Result "${etiquette}_FICHIERS" "$($arbre.Fichiers)"
    $zip = Join-Path $env:RUNNER_TEMP "lecteur-etude-$etiquette.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    # Même cmdlet que la fabrication : Compress-Archive du dossier dist/VHSRestoreAI.
    Compress-Archive -Path dist\VHSRestoreAI -DestinationPath $zip
    $zipOctets = [int64](Get-Item -LiteralPath $zip).Length
    $zipMo = ($zipOctets / 1MB).ToString("0.00", [Globalization.CultureInfo]::InvariantCulture)
    Write-Result "${etiquette}_ZIP_OCTETS" "$zipOctets"
    Write-Result "${etiquette}_ZIP_MO" $zipMo
    $inv = Get-Inventory "dist\VHSRestoreAI"
    $inv | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $env:RUNNER_TEMP "inventaire-$etiquette.json") -Encoding utf8
    Remove-Item -Recurse -Force dist, build
    return @{ Inventaire = $inv; Zip = $zipOctets; Nu = $arbre.Octets }
}

Write-Output "=== PAQUET SANS QT MULTIMEDIA ==="
$specPath = Join-Path (Get-Location) "VHSRestoreAI.spec"
$specOctets = [IO.File]::ReadAllBytes($specPath)
$specTexte = [Text.Encoding]::UTF8.GetString($specOctets)
$cherche = '"tkinter", "pytest"],'
$remplace = '"tkinter", "pytest", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets"],'
if (-not $specTexte.Contains($cherche)) { throw "Le bloc excludes du spec n'est pas celui attendu." }
$specAvant = $specTexte.Replace($cherche, $remplace)
[IO.File]::WriteAllText($specPath, $specAvant, (New-Object Text.UTF8Encoding $false))
try {
    $paquetAvant = Invoke-Paquet "AVANT"
} finally {
    [IO.File]::WriteAllBytes($specPath, $specOctets)
}
$specApresOctets = [IO.File]::ReadAllBytes($specPath)
if (([Convert]::ToHexString($specOctets)) -ne ([Convert]::ToHexString($specApresOctets))) {
    throw "Le spec n'a pas été restauré à l'identique."
}
Write-Result "SPEC_RESTAURE" "oui"

Write-Output "=== PAQUET AVEC QT MULTIMEDIA (spec du dépôt) ==="
$paquetApres = Invoke-Paquet "APRES"
if ($paquetAvant.Zip -lt 1 -or $paquetApres.Zip -lt 1) { throw "Un zip de paquet est vide." }
$invAvant = $paquetAvant.Inventaire
$invApres = $paquetApres.Inventaire

$ajouts = [System.Collections.Generic.List[string]]::new()
$retraits = [System.Collections.Generic.List[string]]::new()
$modifies = [System.Collections.Generic.List[string]]::new()
$octetsAjouts = [int64]0
$octetsRetraits = [int64]0
$deltaCommuns = [int64]0
foreach ($cle in $invApres.Keys) {
    if (-not $invAvant.Contains($cle)) {
        $ajouts.Add("$cle $($invApres[$cle])")
        $octetsAjouts += [int64]$invApres[$cle]
    } elseif ([int64]$invApres[$cle] -ne [int64]$invAvant[$cle]) {
        $diff = [int64]$invApres[$cle] - [int64]$invAvant[$cle]
        $modifies.Add("$cle avant=$($invAvant[$cle]) apres=$($invApres[$cle]) delta=$diff")
        $deltaCommuns += $diff
    }
}
foreach ($cle in $invAvant.Keys) {
    if (-not $invApres.Contains($cle)) {
        $retraits.Add("$cle $($invAvant[$cle])")
        $octetsRetraits += [int64]$invAvant[$cle]
    }
}
$liste = Join-Path $sortie "fichiers-ajoutes.txt"
$lignesListe = @(
    "AJOUTS_OCTETS $octetsAjouts",
    "RETRAITS_OCTETS $octetsRetraits",
    "COMMUNS_DELTA_OCTETS $deltaCommuns",
    "--- ajouts ---"
) + $ajouts + @("--- retraits ---") + $retraits + @("--- modifies ---") + $modifies
$lignesListe | Set-Content -LiteralPath $liste -Encoding utf8
Write-Result "AJOUTS_OCTETS" "$octetsAjouts"
Write-Result "AJOUTS_NOMBRE" "$($ajouts.Count)"
Write-Result "RETRAITS_OCTETS" "$octetsRetraits"
Write-Result "RETRAITS_NOMBRE" "$($retraits.Count)"
Write-Result "COMMUNS_DELTA_OCTETS" "$deltaCommuns"
Write-Result "COMMUNS_MODIFIES" "$($modifies.Count)"

# Ne pas confondre avec tools/ffmpeg/ffmpeg.exe, copié dans les deux paquets.
$motif = '(?i)qt6multimedia|qtmultimedia|ffmpegmediaplugin|(^|/)av(codec|format|util)-|(^|/)sw(scale|resample)-'
$multiAvant = @($invAvant.Keys | Where-Object { $_ -match $motif })
$multiApres = @($invApres.Keys | Where-Object { $_ -match $motif })
Write-Result "FICHIERS_MULTIMEDIA_AVANT" "$($multiAvant.Count)"
Write-Result "FICHIERS_MULTIMEDIA_APRES" "$($multiApres.Count)"
Write-Output "=== FICHIERS MULTIMEDIA APRES ==="
$multiApres | Sort-Object | ForEach-Object { Write-Output "MEDIA $_ $($invApres[$_])" }
if ($multiApres.Count -lt 1) {
    throw "Le paquet « après » ne contient aucun fichier Qt Multimedia ni FFmpeg de Qt. La mesure ne vaut pas."
}
if ($multiAvant.Count -gt 0) {
    Write-Output "=== FICHIERS MULTIMEDIA ENCORE PRESENTS AVANT ==="
    $multiAvant | Sort-Object | ForEach-Object { Write-Output "MEDIA_AVANT $_ $($invAvant[$_])" }
    throw "L'exclusion n'a pas retiré Qt Multimedia du paquet « avant »."
}

function Format-Mo([int64]$octets) {
    return ($octets / 1MB).ToString("0.00", [Globalization.CultureInfo]::InvariantCulture)
}
Write-Result "DELTA_ZIP_OCTETS" "$($paquetApres.Zip - $paquetAvant.Zip)"
Write-Result "DELTA_ZIP_MO" (Format-Mo ($paquetApres.Zip - $paquetAvant.Zip))
Write-Result "DELTA_DECOMPRESSE_OCTETS" "$($paquetApres.Nu - $paquetAvant.Nu)"
Write-Result "DELTA_DECOMPRESSE_MO" (Format-Mo ($paquetApres.Nu - $paquetAvant.Nu))
Write-Result "MO_DEFINITION" "1048576"

Write-Output "=== STRIES ==="
$env:PYTHONUTF8 = "1"
$env:PATH = "$PWD\tools\ffmpeg\bin;$env:PATH"
& python (Join-Path $repo ".github\workflows\mesure-stries-n13.py") --sortie $sortie
if ($LASTEXITCODE -ne 0) { throw "La mesure des stries a échoué ($LASTEXITCODE)" }
Write-Output "=== FIN ==="
