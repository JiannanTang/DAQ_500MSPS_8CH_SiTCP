@echo off
setlocal
set "PYTHONPATH=%~dp0src"
python -m sitcp_host %*
if errorlevel 1 pause
endlocal
