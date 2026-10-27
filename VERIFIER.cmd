@echo off
setlocal
cd /d "%~dp0"
title Cap Avenir - Verification CI locale
if not exist ".venv\Scripts\python.exe" (
    echo Lancez d'abord LANCER.cmd pour installer l'environnement.
    goto :error
)
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m compileall -q app.py provider.py workflow.py storage.py launch.py setup_secret.py scripts tests
if errorlevel 1 goto :error
node --check static/app.js
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto :error
".venv\Scripts\python.exe" scripts/package_ci.py
if errorlevel 1 goto :error
echo.
echo Verification reussie. Archive : ci-output\Cap-Avenir-CI.zip
echo Aucun appel API n'a ete effectue.
pause
exit /b 0
:error
echo.
echo Verification en echec. Consultez le message ci-dessus.
pause
exit /b 1
