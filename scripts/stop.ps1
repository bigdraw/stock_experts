# Stock Analysis Platform - Stop Script (Windows PowerShell)
# Usage: scripts\stop.bat

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = "$PSScriptRoot\.service-pids.json"

Write-Host ""
Write-Host "  Stopping..." -ForegroundColor Yellow

$found = $false

# 1. PID file
if (Test-Path $PidFile) {
    $Pids = Get-Content $PidFile | ConvertFrom-Json
    foreach ($key in @("backend","frontend")) {
        $pid_val = $Pids.$key
        if ($pid_val) {
            try { Stop-Process -Id $pid_val -Force -ErrorAction Stop; Write-Host "  $key (PID $pid_val) stopped" -ForegroundColor Green; $found = $true }
            catch {}
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 2. Port scan fallback
foreach ($port in @("8000","5173")) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop; Write-Host "  port $port (PID $($conn.OwningProcess)) stopped" -ForegroundColor Green; $found = $true }
        catch {}
    }
}

if (-not $found) { Write-Host "  Nothing to stop." -ForegroundColor DarkGray }
Write-Host ""
