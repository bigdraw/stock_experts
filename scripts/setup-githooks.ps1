# One-time setup (PowerShell): point git at the repo-shareable githooks/ directory.
# Run after cloning:  pwsh scripts/setup-githooks.ps1
$ErrorActionPreference = "Stop"
$repoRoot = git rev-parse --show-toplevel
if (-not $repoRoot) { Write-Error "not a git repo"; exit 1 }
Set-Location $repoRoot
git config core.hooksPath githooks
Write-Host "core.hooksPath = $(git config core.hooksPath)"
Write-Host "hooks: $((Get-ChildItem githooks).Name -join ', ')"
Write-Host "done. pre-commit + commit-msg now active."
