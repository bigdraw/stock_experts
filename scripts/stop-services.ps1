# Stop backend and frontend services for stock analysis platform
# Usage: .\scripts\stop-services.ps1

$ErrorActionPreference = "Stop"
$pidFile = Join-Path $PSScriptRoot ".service-pids.json"

Write-Host "Stopping Stock Analysis Platform services..." -ForegroundColor Cyan

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found. Services may not be running." -ForegroundColor Yellow
    exit 0
}

# Read PIDs
$pids = Get-Content $pidFile | ConvertFrom-Json
Write-Host "Found services started at: $($pids.startedAt)" -ForegroundColor Gray

# Stop backend
if ($pids.backend) {
    Write-Host "`nStopping backend (PID: $($pids.backend))..." -ForegroundColor Green
    try {
        $process = Get-Process -Id $pids.backend -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $pids.backend -Force
            Write-Host "✓ Backend stopped" -ForegroundColor Green
        } else {
            Write-Host "Backend process not found (already stopped)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Warning: Failed to stop backend: $_" -ForegroundColor Yellow
    }
}

# Stop frontend
if ($pids.frontend) {
    Write-Host "`nStopping frontend (PID: $($pids.frontend))..." -ForegroundColor Green
    try {
        $process = Get-Process -Id $pids.frontend -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $pids.frontend -Force
            Write-Host "✓ Frontend stopped" -ForegroundColor Green
        } else {
            Write-Host "Frontend process not found (already stopped)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Warning: Failed to stop frontend: $_" -ForegroundColor Yellow
    }
}

# Also kill any lingering node/uvicorn processes on our ports
Write-Host "`nCleaning up any lingering processes..." -ForegroundColor Gray

# Kill processes on port 8000 (backend)
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $port8000) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "Killed process on port 8000 (PID: $pid)" -ForegroundColor Gray
    } catch {}
}

# Kill processes on port 5173 (frontend)
$port5173 = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $port5173) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "Killed process on port 5173 (PID: $pid)" -ForegroundColor Gray
    } catch {}
}

# Remove PID file
Remove-Item $pidFile -Force
Write-Host "`n✓ All services stopped" -ForegroundColor Green
