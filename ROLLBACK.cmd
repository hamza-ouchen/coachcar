@echo off
setlocal
cd /d "%~dp0"
title Cap Avenir - Retour a la version precedente
".venv\Scripts\python.exe" scripts/release_manager.py rollback
if errorlevel 1 goto :error
start "" "http://127.0.0.1:8080/#operations"
echo Version precedente restauree. Verifiez le service avant de reautoriser les analyses.
pause
exit /b 0
:error
echo Le retour arriere n'a pas ete realise. Consultez le message ci-dessus.
pause
exit /b 1
