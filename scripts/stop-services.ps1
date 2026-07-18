# Stop backend and frontend services for stock analysis platform
# Usage: .\scripts\stop-services.ps1

$ErrorActionPreference = "Continue"
$pidFile = Join-Path $PSScriptRoot ".service-pids.json"

Write-Host "Stopping Stock Analysis Platform services..." -ForegroundColor Cyan

# Step 1: Kill by PID file
if (Test-Path $pidFile) {
    $pids = Get-Content $pidFile | ConvertFrom-Json
    Write-Host "Found services started at: $($pids.startedAt)" -ForegroundColor Gray

    foreach ($pidValue in @($pids.backend, $pids.frontend)) {
        if ($pidValue) {
            try {
                $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
                if ($proc) {
                    # Kill the entire process tree
                    $proc | ForEach-Object {
                        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($_.Id)" | ForEach-Object {
                            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                        }
                    }
                    Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                    Write-Host "Killed PID $pidValue and children" -ForegroundColor Green
                }
            } catch {
                Write-Host "Warning: Failed to stop PID ${pidValue}: $_" -ForegroundColor Yellow
            }
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "No PID file found." -ForegroundColor Yellow
}

# Step 2: Kill by port (catches processes not tracked by PID file)
Write-Host "`nCleaning up processes on ports 8000 and 5173..." -ForegroundColor Gray

foreach ($port in @(8000, 5173)) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($connections) {
        $procIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $procIds) {
            if ($procId -and $procId -ne 0) {
                try {
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    Write-Host "Killed process on port $port (PID: $procId)" -ForegroundColor Gray
                } catch {}
            }
        }
    }
}

# Step 3: Kill uvicorn processes by command line
Write-Host "Cleaning up uvicorn processes from this project..." -ForegroundColor Gray
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*stock*" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Killed uvicorn process (PID: $($_.ProcessId))" -ForegroundColor Gray
    }

# Step 4: Kill node processes from this project's frontend
Write-Host "Cleaning up node processes from this project..." -ForegroundColor Gray
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*stock*frontend*" -or $_.CommandLine -like "*vite*" } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Killed node process (PID: $($_.ProcessId))" -ForegroundColor Gray
    }

# Step 5: Wait and verify
Start-Sleep -Seconds 2
$remaining8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$remaining5173 = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue

if ($remaining8000 -or $remaining5173) {
    Write-Host "`nWarning: Some processes still running!" -ForegroundColor Yellow
    if ($remaining8000) { Write-Host "  Port 8000 still in use" -ForegroundColor Yellow }
    if ($remaining5173) { Write-Host "  Port 5173 still in use" -ForegroundColor Yellow }
} else {
    Write-Host "`n[OK] All services stopped" -ForegroundColor Green
}
