@echo off
rem Liga o simulado ao vivo (sem ordens reais). Deixe esta janela aberta durante o pregao.
rem Como nenhuma estrategia foi aprovada ainda, roda em modo DEMONSTRACAO.
rem Para desligar: feche a janela ou use "PARAR O SINDICATO.bat".
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" laboratorio.py vendedor --demonstracao cruzamento_medias rompimento reversao_ifr2
pause
