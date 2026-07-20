#!/usr/bin/env bash
# 一键停止 backend + frontend 开发服务
# 与 scripts/dev.sh 配套使用。
#
# 行为：
#   1. 读取 scripts/.service-pids.json，按 PID kill 进程；
#   2. 若 PID 文件不存在或不完整，则按端口 8000 / 5173 查找并 kill；
#   3. 清理 PID 文件。
#
# PID 文件支持两种格式：
#   {"backend": 1234, "frontend": 5678}                  # dev.sh 写入
#   {"backend": [1,2,3], "frontend": [4,5,6]}           # 旧版 start-services.ps1 写入
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/scripts/.service-pids.json"

BACKEND_PORT=8000
FRONTEND_PORT=5173

# kill 一个 PID（容错：进程可能已退出）
kill_pid() {
    local pid="$1"
    if [[ -z "${pid:-}" ]]; then return 0; fi
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "  PID $pid: not running"
        return 0
    fi
    echo "  Stopping PID $pid ..."
    kill "$pid" 2>/dev/null || true
}

# 从 JSON 字段提取 PID 列表，兼容 number 与 array
extract_pids() {
    local field="$1"
    if [[ ! -f "$PID_FILE" ]]; then return 0; fi
    # 优先用 python3（跨平台、对 JSON 严格）
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "
import json,sys
try:
    d=json.load(open(r'''$PID_FILE'''))
except Exception:
    sys.exit(0)
v=d.get('$field')
if isinstance(v,list):
    for p in v: print(p)
elif v is not None:
    print(v)
" 2>/dev/null
        return 0
    fi
    # 退回到 grep+sed：提取字段后的数字（首组）
    grep -o "\"$field\"[[:space:]]*:[[:space:]]*\\[[0-9,[:space:]]*\\]\\|\"$field\"[[:space:]]*:[[:space:]]*[0-9]*" "$PID_FILE" \
        | grep -o '[0-9]\\+' || true
}

# 按端口查活进程并 kill（PID 文件缺失或不完整时的兜底）
kill_by_port() {
    local port="$1"
    local label="$2"
    local pids=""
    if command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    elif command -v netstat >/dev/null 2>&1; then
        # Windows Git Bash / Linux netstat
        pids=$(netstat -ano 2>/dev/null | grep -E "[:.]$port\b" | grep LISTENING \
               | awk '{print $NF}' | sort -u || true)
    fi
    if [[ -z "${pids// /}" ]]; then
        echo "  $label (port $port): no process found"
        return 0
    fi
    for p in $pids; do
        kill_pid "$p"
    done
}

echo "Stopping dev services..."

stopped_any=0

if [[ -f "$PID_FILE" ]]; then
    echo "Reading PID file: $PID_FILE"
    backend_pids=$(extract_pids backend)
    frontend_pids=$(extract_pids frontend)
    if [[ -n "${backend_pids}${frontend_pids}" ]]; then
        stopped_any=1
        echo "[backend]"
        if [[ -z "$backend_pids" ]]; then
            kill_by_port $BACKEND_PORT backend
        else
            for p in $backend_pids; do kill_pid "$p"; done
        fi
        echo "[frontend]"
        if [[ -z "$frontend_pids" ]]; then
            kill_by_port $FRONTEND_PORT frontend
        else
            for p in $frontend_pids; do kill_pid "$p"; done
        fi
    else
        echo "  PID file unreadable; falling back to port scan."
    fi
else
    echo "No PID file found at $PID_FILE; scanning by port."
fi

if [[ "$stopped_any" -eq 0 ]] || [[ ! -f "$PID_FILE" ]]; then
    # 兜底：按端口清理
    echo "[backend]   (port $BACKEND_PORT)"
    kill_by_port $BACKEND_PORT backend
    echo "[frontend] (port $FRONTEND_PORT)"
    kill_by_port $FRONTEND_PORT frontend
fi

# 等待并强杀残留（给 2s 优雅退出）
sleep 1
for port in $BACKEND_PORT $FRONTEND_PORT; do
    if command -v lsof >/dev/null 2>&1; then
        remaining=$(lsof -ti tcp:"$port" 2>/dev/null || true)
        if [[ -n "$remaining" ]]; then
            echo "Force killing leftovers on port $port: $remaining"
            for p in $remaining; do kill -9 "$p" 2>/dev/null || true; done
        fi
    fi
done

# 清理 PID 文件
if [[ -f "$PID_FILE" ]]; then
    rm -f "$PID_FILE"
    echo "Removed PID file: $PID_FILE"
fi

echo "Done."
