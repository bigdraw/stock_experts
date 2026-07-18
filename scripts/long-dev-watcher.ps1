$ErrorActionPreference = "SilentlyContinue"

$projectRoot = $PSScriptRoot | Split-Path -Parent
$opencodeDb = Join-Path $env:USERPROFILE ".local\share\opencode\opencode.db"
$statusFile = Join-Path $projectRoot ".ai\STATUS.md"
$recoveryNote = Join-Path $projectRoot ".ai\cache\recovery-note.md"
$cacheDir = Join-Path $projectRoot ".ai\cache"
$retryCountFile = Join-Path $cacheDir ".watcher-retry-count"
$stuckThresholdMin = 30
$maxRetries = 3

if (-not (Test-Path $cacheDir)) {
    New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
}

$retryCount = 0
if (Test-Path $retryCountFile) {
    $retryCount = [int](Get-Content $retryCountFile -Raw).Trim()
}

$anomalies = @()
$stuck = $false
$opencodeProcess = Get-Process -Name "opencode" -ErrorAction SilentlyContinue

if ($opencodeProcess) {
    if (Test-Path $opencodeDb) {
        $lastSession = & sqlite3 $opencodeDb "SELECT status, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 1;" 2>$null
        if ($lastSession) {
            $parts = $lastSession -split '\|'
            $status = $parts[0]
            $updatedAt = $parts[1]
            if ($status -ne "idle" -and $updatedAt) {
                $lastUpdate = [DateTime]::Parse($updatedAt)
                $minutesAgo = ((Get-Date) - $lastUpdate).TotalMinutes
                if ($minutesAgo -gt $stuckThresholdMin) {
                    $stuck = $true
                    $anomalies += "opencode 进程卡死：$([math]::Round($minutesAgo)) 分钟无活动（状态: $status）"
                }
            }
        }
    }
} else {
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
                    $anomalies += "opencode 进程已退出，最后会话状态为 $status（$([math]::Round($minutesAgo)) 分钟前），可能崩溃"
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
            $anomalies += "implement 阶段检测到未提交工作"
        }
    }
}

if ($anomalies.Count -gt 0) {
    $now = [DateTime]::Now.ToString("yyyy-MM-dd HH:mm:ss")
    $autoResume = $stuck -and ($retryCount -lt $maxRetries)
    $noteContent = @"
# Recovery Note

检测到以下异常（$now）：

"@
    foreach ($a in $anomalies) {
        $noteContent += "- $a`n"
    }

    if ($autoResume) {
        $nextRetry = $retryCount + 1
        $noteContent += @"

- auto_resume: true
- retry_count: $nextRetry / $maxRetries
- action: 自动继续执行 STATUS.md 中的 current_task 和 next_action
"@
        Set-Content -Path $retryCountFile -Value "$nextRetry" -Encoding UTF8
        Write-Host "long-dev watcher: 检测到卡死，准备自动恢复（第 $nextRetry 次）" -ForegroundColor Yellow
    } else {
        if ($retryCount -ge $maxRetries) {
            $noteContent += @"

- auto_resume: false
- retry_count: $retryCount / $maxRetries（已达上限，停止自动恢复）
- action: 需要用户手动干预
"@
            Write-Host "long-dev watcher: 已达最大重试次数，停止自动恢复" -ForegroundColor Red
        } else {
            $noteContent += @"

- auto_resume: false
- action: 运行 /resume 查看详细状态，根据提示选择 commit/stash/revert/retry
"@
        }
        if (Test-Path $retryCountFile) {
            Remove-Item $retryCountFile -Force
        }
    }

    Set-Content -Path $recoveryNote -Value $noteContent -Encoding UTF8
    Write-Host "long-dev watcher: 检测到 $($anomalies.Count) 个异常，已写入 recovery-note.md" -ForegroundColor Yellow

    if ($stuck -and $opencodeProcess) {
        Write-Host "long-dev watcher: 正在终止卡死的 opencode 进程..." -ForegroundColor Red
        $opencodeProcess | Stop-Process -Force
        Start-Sleep -Seconds 3
    }

    if ($autoResume) {
        Write-Host "long-dev watcher: 正在重启 opencode 自动恢复..." -ForegroundColor Cyan
        $prompt = "读取 .ai/cache/recovery-note.md 和 .ai/STATUS.md，自动继续执行当前任务，不要等待用户确认"
        Start-Process -FilePath "opencode" -ArgumentList "run", "--continue", "--auto", "--prompt", "`"$prompt`"" -WorkingDirectory $projectRoot -WindowStyle Normal
    }
} else {
    if (Test-Path $recoveryNote) {
        Remove-Item $recoveryNote -Force
    }
    if (Test-Path $retryCountFile) {
        Remove-Item $retryCountFile -Force
    }
    Write-Host "long-dev watcher: 状态正常" -ForegroundColor Green
}
