#!/usr/bin/env bash
# One-time setup: point git at the repo-shareable githooks/ directory.
# Run after cloning:  bash scripts/setup-githooks.sh
set -eu
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "not a git repo"; exit 1; }
cd "$REPO_ROOT"
git config core.hooksPath githooks
chmod +x githooks/pre-commit githooks/commit-msg 2>/dev/null || true
echo "core.hooksPath = $(git config core.hooksPath)"
echo "hooks: $(ls githooks)"
echo "done. pre-commit + commit-msg now active."
