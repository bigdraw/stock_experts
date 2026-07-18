$ErrorActionPreference = "SilentlyContinue"

$projectRoot = $PSScriptRoot | Split-Path -Parent
$opencodeDb = Join-Path $env:USERPROFILE ".local\share\opencode\opencode.db"
$statusFile = Join-Path $projectRoot ".ai\STATUS.md"
$recoveryNote = Join-Path $projectRoot ".ai\cache\recovery-note.md"
$cacheDir = Join-Path $projectRoot ".ai\cache"

if (-not (Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
}

$anomalies = @()

$opencodeProcess = Get-Process -Name "opencode" -ErrorAction SilentlyContinue
if (-not $opencodeProcess) {
    if (Test-Path $opencodeDb) {
        $lastSession = & sqlite3 $opencodeDb "SELECT status, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 1;" 2>$null
        if ($lastSession) {
            $parts = $lastSession -split '\|'
            $status = $parts[0]
            $updatedAt = $parts[1]
            if ($status -ne "idle" -and $updatedAt) {
                $lastUpdate = [DateTime]::Parse($updatedAt)
                $minutesAgo = ((Get-Date) - $lastUpdate).TotalMinutes
                if ($minutesAgo -gt 10) {
                    $anomalies += "opencode 进程已退出，但最后会话状态为 $status（$([math]::Round($minutesAgo)) 分钟前），可能崩溃"
                }
            }
        }
    }
}

if (Test-Path $statusFile) {
    $statusContent = Get-Content $statusFile -Raw
    $lastCommitMatch = [regex]::Match($statusContent, "last_commit:\s*(\w+)")
    if ($lastCommitMatch.Success) {
        $statusCommit = $lastCommitMatch.Groups[1].Value
        $gitHead = & git -C $projectRoot rev-parse HEAD 2>$null
        if ($gitHead -and $statusCommit -ne $gitHead.Substring(0, 7)) {
            $anomalies += "STATUS.md 的 last_commit ($statusCommit) 与 git HEAD ($($gitHead.Substring(0,7))) 不一致"
        }
    }
    
    $phaseMatch = [regex]::Match($statusContent, "current_phase:\s*(\w+)")
    if ($phaseMatch.Success -and $phaseMatch.Groups[1].Value -eq "implement") {
        $gitStatus = & git -C $projectRoot status --porcelain 2>$null
        if ($gitStatus) {
            $anomalies += "implement 阶段检测到未提交工作，建议 commit 或 stash"
        }
    }
}

if ($anomalies.Count -gt 0) {
    $noteContent = @"
# Recovery Note

检测到以下异常（$([DateTime]::Now.ToString("yyyy-MM-dd HH:mm:ss"))）：

"@
    foreach ($a in $anomalies) {
        $noteContent += "- $a`n"
    }
    $noteContent += @"

建议操作：
- 运行 /resume 查看详细状态
- 根据提示选择 commit/stash/revert/retry
"@
    Set-Content -Path $recoveryNote -Value $noteContent -Encoding UTF8
    Write-Host "long-dev watcher: 检测到 $($anomalies.Count) 个异常，已写入 recovery-note.md" -ForegroundColor Yellow
} else {
    if (Test-Path $recoveryNote) {
        Remove-Item $recoveryNote -Force
    }
    Write-Host "long-dev watcher: 状态正常" -ForegroundColor Green
}
