#!/usr/bin/env bash
# 一键停止 Stock Analysis Platform
# Linux / macOS / Windows (Git Bash)
# 用法：bash scripts/stop.sh

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/scripts/.service-pids.json"

echo "🛑 Stopping Stock Analysis Platform..."

killed=0

# 1. 从 PID 文件 kill
if [ -f "$PID_FILE" ]; then
    for key in backend frontend; do
        pid=$(grep -o "\"$key\":[ ]*[0-9]*" "$PID_FILE" | grep -o '[0-9]*$' 2>/dev/null || true)
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null && { echo "   $key (PID $pid) killed"; killed=1; } || true
        fi
    done
    rm -f "$PID_FILE"
fi

# 2. 按端口兜底 kill
for port in 8000 5173; do
    if command -v lsof &>/dev/null; then
        pids=$(lsof -ti :$port 2>/dev/null || true)
        for pid in $pids; do
            kill "$pid" 2>/dev/null && { echo "   port $port (PID $pid) killed"; killed=1; } || true
        done
    fi
    if command -v netstat &>/dev/null; then
        pids=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $NF}' | sort -u || true)
        for pid in $pids; do
            [ "$pid" = "0" ] && continue
            kill "$pid" 2>/dev/null && { echo "   port $port (PID $pid) killed"; killed=1; } || true
        done
    fi
done

# 3. 强杀残留
sleep 1
for port in 8000 5173; do
    if command -v lsof &>/dev/null; then
        pids=$(lsof -ti :$port 2>/dev/null || true)
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null && { echo "   port $port (PID $pid) force-killed"; } || true
        done
    fi
done

if [ "$killed" = "0" ]; then
    echo "   No services found running."
else
    echo "✅ Stopped."
fi
