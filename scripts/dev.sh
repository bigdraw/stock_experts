#!/usr/bin/env bash
# 一键启动开发环境（backend + frontend）
# 用法：bash scripts/dev.sh
# 停止：bash scripts/stop-services.sh 或 Ctrl+C

set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Starting Stock Analysis Platform (dev mode)..."
echo ""

# Backend
echo "📡 Starting backend (uvicorn :8000)..."
cd "$ROOT/backend"
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "  backend PID: $BACKEND_PID"

# Frontend
echo "🖥️  Starting frontend (vite :5173)..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
echo "  frontend PID: $FRONTEND_PID"

echo ""
echo "✅ Platform running:"
echo "   Backend API:  http://localhost:8000  (docs: /docs)"
echo "   Frontend:      http://localhost:5173"
echo ""
echo "   Press Ctrl+C to stop both."

# Save PIDs
echo "{\"backend\": $BACKEND_PID, \"frontend\": $FRONTEND_PID}" > "$ROOT/scripts/.service-pids.json"

# Wait for either to exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
