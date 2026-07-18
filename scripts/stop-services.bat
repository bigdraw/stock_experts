@echo off
REM Stop services wrapper for Windows
powershell -ExecutionPolicy Bypass -File "%~dp0stop-services.ps1"
pause
