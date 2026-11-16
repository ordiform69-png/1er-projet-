@echo off
rem Installation de VHS Restore AI.
rem Options : -AvecIA (Real-ESRGAN)  -AvecQTGMC (VapourSynth + QTGMC, Python 3.12+)  -AvecPoussieres (Analog Repair : poussières, bruit de bande)  -AvecSon (DeepFilterNet)  -AvecCouleurs (colorisation des photos noir et blanc, DDColor)
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
  echo Python 3.10 ou plus recent est requis : https://www.python.org/downloads/
  echo Cochez "Add python.exe to PATH" pendant son installation.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto erreur
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto erreur
set "QTGMC="
set "POUSSIERES="
for %%a in (%*) do if /i "%%~a"=="-AvecPoussieres" set "POUSSIERES=1"
if defined POUSSIERES (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-poussieres.txt || goto erreur
)
set "COULEURS="
for %%a in (%*) do if /i "%%~a"=="-AvecCouleurs" set "COULEURS=1"
if defined COULEURS (
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-couleurs.txt || goto erreur
)
for %%a in (%*) do if /i "%%~a"=="-AvecQTGMC" set "QTGMC=1"
if defined QTGMC (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
  if errorlevel 1 (
    echo QTGMC demande Python 3.12 ou plus : supprimez le dossier .venv, installez Python 3.12+ et relancez.
    goto erreur
  )
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-qtgmc.txt || goto erreur
  ".venv\Scripts\vapoursynth.exe" config || goto erreur
)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\installer_outils.ps1" %* || goto erreur
echo.
echo Installation terminee. Double-cliquez sur lancer.bat pour demarrer.
pause
exit /b 0
:erreur
echo.
echo L'installation a echoue. Verifiez votre connexion Internet et relancez installer.bat.
pause
exit /b 1
