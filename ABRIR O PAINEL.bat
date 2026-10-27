@echo off
rem Atualiza o painel com tudo o que o robo fez e abre no navegador.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" laboratorio.py painel
