@echo off
REM Start services wrapper for Windows
powershell -ExecutionPolicy Bypass -File "%~dp0start-services.ps1"
pause
