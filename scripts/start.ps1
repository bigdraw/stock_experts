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
# 用 cmd /c 包裹，避免 Start-Process 找到 .ps1 而非 .cmd
$backend = Start-Process -FilePath "cmd" -ArgumentList "/c","uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -PassThru -WindowStyle Minimized
Write-Host "   PID: $($backend.Id)"

Start-Sleep -Seconds 2

# ---- Frontend ----
Write-Host "🖥️  Frontend (vite :5173)..."
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "   Installing deps..."
    # npm.cmd 而非 npm（避免 PowerShell 找到 .ps1）
    cmd /c "npm install"
}
# 同样用 cmd /c 包裹 npm run dev
$frontend = Start-Process -FilePath "cmd" -ArgumentList "/c","npm run dev" -PassThru -WindowStyle Minimized
Write-Host "   PID: $($frontend.Id)"

# ---- Save PIDs ----
$Pids = @{ backend = $backend.Id; frontend = $frontend.Id }
$Pids | ConvertTo-Json | Set-Content "$PSScriptRoot\.service-pids.json"

Write-Host ""
Write-Host "✅ Running:" -ForegroundColor Green
Write-Host "   Backend:  http://localhost:8000  (docs: /docs)"
Write-Host "   Frontend: http://localhost:5173"
Write-Host ""
Write-Host "   Stop: powershell -File scripts\stop.ps1  (or close this window)"

# 等待 backend 进程退出
$backend.WaitForExit()
