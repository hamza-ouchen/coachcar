@echo off
setlocal
cd /d "%~dp0"
title Cap Avenir
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, langgraph, openai, dotenv, httpx" >nul 2>&1
if errorlevel 1 (
    echo Installation des dependances du projet...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)
if not exist ".env" (
    echo Configuration locale de la cle OpenRouter. Entree masquee.
    ".venv\Scripts\python.exe" setup_secret.py
    if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Le lancement a rencontre un probleme. Consultez le message ci-dessus.
pause
exit /b 1
