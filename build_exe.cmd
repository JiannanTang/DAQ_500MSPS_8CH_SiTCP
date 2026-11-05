@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_exe.ps1" %*
if errorlevel 1 pause
endlocal
