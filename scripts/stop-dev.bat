@echo off
REM 一键停止 backend + frontend 开发服务（Windows 入口）
REM 与 scripts/dev.sh 配套使用。
REM
REM 优先调用 scripts/stop.sh（Git Bash / WSL）；
REM 若无 bash 环境，则回退到 PowerShell 版 scripts/stop-services.ps1。

setlocal

set "SCRIPT_DIR=%~dp0"
set "STOP_SH=%SCRIPT_DIR%stop.sh"
set "STOP_PS1=%SCRIPT_DIR%stop-services.ps1"

where bash >nul 2>nul
if %errorlevel%==0 (
    bash "%STOP_SH%" %*
    goto :end
)

where git >nul 2>nul
if %errorlevel%==0 (
    for /f "delims=" %%G in ('where git') do set "GIT_EXE=%%G"
    if exist "%GIT_EXE%" (
        for %%I in ("%GIT_EXE%") do set "GIT_DIR=%%~dpI"
        set "BASH_EXE=%GIT_DIR%bin\bash.exe"
        if exist "%BASH_EXE%" (
            "%BASH_EXE%" "%STOP_SH%" %*
            goto :end
        )
    )
)

if exist "%STOP_PS1%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%STOP_PS1%" %*
    goto :end
)

echo Could not find bash or stop-services.ps1 to stop services. >&2
exit /b 1

:end
endlocal
