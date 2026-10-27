@echo off
rem Liga o bot do Discord do Sindicato (/organizar, /placar, /vendedor, /parar, /religar).
rem Deixe esta janela aberta. O token fica no arquivo .env (DISCORD_BOT_TOKEN).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" laboratorio.py bot
pause
