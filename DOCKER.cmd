@echo off
setlocal
cd /d "%~dp0"
title Cap Avenir - Preparation Docker
".venv\Scripts\python.exe" scripts/release_manager.py prepare-demo
if errorlevel 1 goto :error
if not exist "runtime\deployment.json" (
    ".venv\Scripts\python.exe" scripts/release_manager.py bootstrap
    if errorlevel 1 goto :error
)
start "" "http://127.0.0.1:8787/#operations"
echo Les versions sont preparees. Approuvez une candidate dans Exploitation avant DEPLOYER.cmd.
pause
exit /b 0
:error
echo Verifiez que Docker Desktop est demarre. Consultez le message ci-dessus.
pause
exit /b 1
