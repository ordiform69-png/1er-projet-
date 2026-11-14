@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" call installer.bat
start "" ".venv\Scripts\pythonw.exe" -m vhs_restore
