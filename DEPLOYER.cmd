@echo off
setlocal
cd /d "%~dp0"
title Cap Avenir - Deploiement approuve
".venv\Scripts\python.exe" scripts/release_manager.py deploy
if errorlevel 1 goto :error
start "" "http://127.0.0.1:8787/#operations"
echo Version disponible. Verifiez-la puis reautorisez les analyses dans Exploitation.
pause
exit /b 0
:error
echo Le deploiement n'a pas ete valide. Consultez le message ci-dessus.
pause
exit /b 1
