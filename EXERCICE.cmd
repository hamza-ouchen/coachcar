@echo off
setlocal
cd /d "%~dp0"
title Cap Avenir - Exercice Docker isole
".venv\Scripts\python.exe" scripts/release_manager.py prepare-demo
if errorlevel 1 goto :error
".venv\Scripts\python.exe" scripts/rehearse.py
if errorlevel 1 goto :error
echo Exercice termine : livrables\exercice-docker.json
echo Les conteneurs de test ont ete supprimes. Votre historique est preserve.
pause
exit /b 0
:error
echo Echec de l'exercice. Consultez le message ci-dessus.
pause
exit /b 1
