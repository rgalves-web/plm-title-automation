@echo off
rem minorh — o comando do operador. Encaminha para o pacote Python.
set "PYTHONPATH=%~dp0"
python -X utf8 -m src.minorh %*
