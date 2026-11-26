@echo off
rem Fabrique l'exe de VHS Restore AI sur ce PC. Options : -SansTests  -TousLesTests  -SansMiseAJour
chcp 65001 >nul
set "ICI=%~dp0"
pushd "%ICI%"
if errorlevel 1 (
  echo Impossible d'ouvrir ce dossier. S'il est sur un disque reseau, copiez-le sur l'ordinateur.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\fabriquer_exe.ps1" %*
if errorlevel 1 (
  echo.
  echo La fabrication a echoue : lisez les messages ci-dessus.
  popd
  pause
  exit /b 1
)
popd
echo.
echo Fabrication terminee.
pause
