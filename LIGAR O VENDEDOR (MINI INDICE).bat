@echo off
rem Liga o simulado ao vivo do MINI INDICE (sem ordens reais), no horario da B3 (10h-17h).
rem Como nenhuma estrategia foi aprovada ainda, roda em modo DEMONSTRACAO.
rem Para desligar: feche a janela ou use "PARAR O SINDICATO.bat" (desliga todos os mercados).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" laboratorio.py vendedor --mercado win --demonstracao macd reversao_ifr2
pause
