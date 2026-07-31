# Stock Analysis Platform - Start Script (Windows PowerShell)
# Usage: scripts\start.bat or powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# Stop:  scripts\stop.bat

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "  Stock Analysis Platform" -ForegroundColor White
Write-Host "  --------------------" -ForegroundColor DarkGray
Write-Host ""

# ---- Backend ----
Write-Host "  [1/2] Backend (port 8000)..." -ForegroundColor Cyan
Set-Location "$Root\backend"
if (-not (Test-Path ".venv")) {
    Write-Host "       First run: installing deps..." -ForegroundColor DarkGray
    uv sync
}
$backend = Start-Process -FilePath "cmd" -ArgumentList "/c","uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -PassThru -WindowStyle Minimized
Write-Host "       PID: $($backend.Id)" -ForegroundColor DarkGray
Start-Sleep -Seconds 3

# ---- Frontend ----
Write-Host "  [2/2] Frontend (port 5173)..." -ForegroundColor Cyan
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "       First run: installing deps..." -ForegroundColor DarkGray
    cmd /c "npm install"
}
$frontend = Start-Process -FilePath "cmd" -ArgumentList "/c","npm run dev" -PassThru -WindowStyle Minimized
Write-Host "       PID: $($frontend.Id)" -ForegroundColor DarkGray

# ---- Save PIDs ----
$Pids = @{ backend = $backend.Id; frontend = $frontend.Id }
$Pids | ConvertTo-Json | Set-Content "$PSScriptRoot\.service-pids.json"

Write-Host ""
Write-Host "  Backend:  http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "  Press Ctrl+C or run scripts\stop.bat to stop." -ForegroundColor DarkGray
Write-Host ""

# Wait for backend process
$backend.WaitForExit()
