# Stop backend and frontend services for stock analysis platform
# Usage: .\scripts\stop-services.ps1
# Only kills processes recorded in the PID file - no guessing.

$ErrorActionPreference = "Continue"
$pidFile = Join-Path $PSScriptRoot ".service-pids.json"

Write-Host "Stopping Stock Analysis Platform services..." -ForegroundColor Cyan

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found. Services may not be running." -ForegroundColor Yellow
    Write-Host "If services are running, stop them manually." -ForegroundColor Yellow
    exit 0
}

# Read PIDs
$pids = Get-Content $pidFile | ConvertFrom-Json
Write-Host "Found services started at: $($pids.startedAt)" -ForegroundColor Gray

# Collect all PIDs to kill (flatten backend + frontend arrays)
$allPids = @()

# backend can be a single int (old format) or array (new format)
if ($pids.backend) {
    if ($pids.backend -is [array]) {
        $allPids += $pids.backend
    } else {
        $allPids += $pids.backend
    }
}

if ($pids.frontend) {
    if ($pids.frontend -is [array]) {
        $allPids += $pids.frontend
    } else {
        $allPids += $pids.frontend
    }
}

# Remove duplicates and nulls
$allPids = $allPids | Where-Object { $_ } | Sort-Object -Unique

Write-Host "PIDs to stop: $($allPids -join ', ')" -ForegroundColor Gray

# Kill each recorded PID
$killed = 0
$alreadyStopped = 0
foreach ($procId in $allPids) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        $killed++
    } else {
        $alreadyStopped++
    }
}

# Remove PID file
Remove-Item $pidFile -Force -ErrorAction SilentlyContinue

# Wait and verify
Start-Sleep -Seconds 1

# Verify only our PIDs are gone (don't check ports - other programs may use them)
$stillRunning = 0
foreach ($procId in $allPids) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        $stillRunning++
        Write-Host "Warning: PID $procId still running" -ForegroundColor Yellow
    }
}

Write-Host "`nResults: killed=$killed, already stopped=$alreadyStopped, still running=$stillRunning" -ForegroundColor Gray

if ($stillRunning -eq 0) {
    Write-Host "[OK] All services stopped" -ForegroundColor Green
} else {
    Write-Host "[WARN] $stillRunning process(es) could not be stopped" -ForegroundColor Yellow
}
