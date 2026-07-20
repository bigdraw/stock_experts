# 一键启动 Stock Analysis Platform（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# 停止：powershell -ExecutionPolicy Bypass -File scripts\stop.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "🚀 Starting Stock Analysis Platform..." -ForegroundColor Cyan
Write-Host ""

# ---- Backend ----
Write-Host "📡 Backend (uvicorn :8000)..."
Set-Location "$Root\backend"
if (-not (Test-Path ".venv")) {
    Write-Host "   Creating venv..."
    uv sync
}
$backend = Start-Process -FilePath "uv" -ArgumentList "run","uvicorn","app.main:app","--reload","--host","0.0.0.0","--port","8000" -PassThru -NoNewWindow
Write-Host "   PID: $($backend.Id)"

# ---- Frontend ----
Write-Host "🖥️  Frontend (vite :5173)..."
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "   Installing deps..."
    npm install
}
$frontend = Start-Process -FilePath "npm" -ArgumentList "run","dev" -PassThru -NoNewWindow
Write-Host "   PID: $($frontend.Id)"

# ---- Save PIDs ----
$Pids = @{ backend = $backend.Id; frontend = $frontend.Id }
$Pids | ConvertTo-Json | Set-Content "$PSScriptRoot\.service-pids.json"

Write-Host ""
Write-Host "✅ Running:" -ForegroundColor Green
Write-Host "   Backend:  http://localhost:8000  (docs: /docs)"
Write-Host "   Frontend: http://localhost:5173"
Write-Host ""
Write-Host "   Stop: powershell -File scripts\stop.ps1  (or Ctrl+C)"

# 等待子进程
try {
    while ($true) { Start-Sleep -Seconds 1 }
} catch {
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
}
