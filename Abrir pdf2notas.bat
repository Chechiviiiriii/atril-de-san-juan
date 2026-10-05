@echo off
:: Lanzador de pdf2notas
:: Para usar un Python portátil, cambia la variable PYTHON a su ruta, p. ej.:
::   set PYTHON=python\python.exe
set PYTHON=pythonw

cd /d "%~dp0"
start "" %PYTHON% app.py %*
