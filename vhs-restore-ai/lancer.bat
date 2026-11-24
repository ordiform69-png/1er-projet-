@echo off
rem cmd refuse « cd » vers \\serveur\... (disque reseau). On lance avec le chemin complet.
set "ICI=%~dp0"
if not exist "%ICI%.venv\Scripts\pythonw.exe" call "%ICI%installer.bat"
start "" /D "%ICI%" "%ICI%.venv\Scripts\pythonw.exe" -m vhs_restore
