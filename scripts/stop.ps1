# 一键停止 Stock Analysis Platform（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\stop.ps1

$Root = Split-Path -Parent $PSScriptRoot
$PidFile = "$PSScriptRoot\.service-pids.json"

Write-Host "🛑 Stopping Stock Analysis Platform..." -ForegroundColor Cyan

$killed = $false

# 1. 从 PID 文件 kill
if (Test-Path $PidFile) {
    $Pids = Get-Content $PidFile | ConvertFrom-Json
    foreach ($key in @("backend","frontend")) {
        $pid_val = $Pids.$key
        if ($pid_val) {
            try {
                Stop-Process -Id $pid_val -Force -ErrorAction Stop
                Write-Host "   $key (PID $pid_val) killed"
                $killed = $true
            } catch { }
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 2. 按端口兜底 kill
foreach ($port in @("8000","5173")) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
            Write-Host "   port $port (PID $($conn.OwningProcess)) killed"
            $killed = $true
        } catch { }
    }
}

if (-not $killed) {
    Write-Host "   No services found running."
} else {
    Write-Host "✅ Stopped." -ForegroundColor Green
}
