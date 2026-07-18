# Start backend and frontend services for stock analysis platform
# Usage: .\scripts\start-services.ps1

$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $PSScriptRoot ".service-pids.json"

Write-Host "Starting Stock Analysis Platform services..." -ForegroundColor Cyan

# Check if services are already running
if (Test-Path $pidFile) {
    Write-Host "Warning: PID file exists. Services may already be running." -ForegroundColor Yellow
    Write-Host "Run .\scripts\stop-services.ps1 first if you want to restart." -ForegroundColor Yellow
    $response = Read-Host "Continue anyway? (y/N)"
    if ($response -ne 'y' -and $response -ne 'Y') {
        exit 0
    }
}

function Get-ChildPids {
    param([int]$ParentPid)
    $children = @()
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentPid" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $children += $_.ProcessId
            $children += Get-ChildPids -ParentPid $_.ProcessId
        }
    return $children
}

# Start backend
Write-Host "`nStarting backend (FastAPI) on port 8000..." -ForegroundColor Green
$backendDir = Join-Path $rootDir "backend"
$backendProcess = Start-Process -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" `
    -WorkingDirectory $backendDir `
    -PassThru `
    -WindowStyle Normal

Write-Host "Backend parent PID: $($backendProcess.Id)" -ForegroundColor Gray

# Wait for backend to initialize and spawn child processes
Start-Sleep -Seconds 5

# Start frontend
Write-Host "`nStarting frontend (Vite) on port 5173..." -ForegroundColor Green
$frontendDir = Join-Path $rootDir "frontend"
$frontendProcess = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm", "run", "dev" `
    -WorkingDirectory $frontendDir `
    -PassThru `
    -WindowStyle Normal

Write-Host "Frontend parent PID: $($frontendProcess.Id)" -ForegroundColor Gray

# Wait for frontend to spawn child processes
Start-Sleep -Seconds 3

# Collect full process trees
$backendPids = @($backendProcess.Id) + @(Get-ChildPids -ParentPid $backendProcess.Id)
$frontendPids = @($frontendProcess.Id) + @(Get-ChildPids -ParentPid $frontendProcess.Id)

# Filter out dead PIDs (process may have exited already)
$backendPids = $backendPids | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }
$frontendPids = $frontendPids | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }

Write-Host "Backend process tree: $($backendPids -join ', ')" -ForegroundColor Gray
Write-Host "Frontend process tree: $($frontendPids -join ', ')" -ForegroundColor Gray

# Save all PIDs
$pids = @{
    backend = $backendPids
    frontend = $frontendPids
    startedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
}
$pids | ConvertTo-Json | Set-Content $pidFile

Write-Host "`n[OK] Services started successfully!" -ForegroundColor Green
Write-Host "  Backend:  http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  Frontend: http://127.0.0.1:5173" -ForegroundColor Cyan
Write-Host "  API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "`nTo stop services, run: .\scripts\stop-services.ps1" -ForegroundColor Gray
