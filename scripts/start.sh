#!/usr/bin/env bash
# 一键启动 Stock Analysis Platform（backend + frontend）
# Linux / macOS / Windows (Git Bash)
# 用法：bash scripts/start.sh
# 停止：bash scripts/stop.sh

set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Starting Stock Analysis Platform..."
echo ""

# ---- Backend ----
echo "📡 Backend (uvicorn :8000)..."
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
    echo "   Creating venv..."
    uv sync
fi
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "   PID: $BACKEND_PID"

# ---- Frontend ----
echo "🖥️  Frontend (vite :5173)..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo "   Installing deps..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!
echo "   PID: $FRONTEND_PID"

# ---- Save PIDs ----
echo "{\"backend\": $BACKEND_PID, \"frontend\": $FRONTEND_PID}" > "$ROOT/scripts/.service-pids.json"

echo ""
echo "✅ Running:"
echo "   Backend:  http://localhost:8000  (docs: /docs)"
echo "   Frontend: http://localhost:5173"
echo ""
echo "   Stop: bash scripts/stop.sh  (or Ctrl+C)"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
