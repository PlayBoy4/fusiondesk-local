#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python3"
PORT="${CLAUDE_DASHBOARD_PORT:-4899}"
LOG="$ROOT/dashboard/logs/dashboard-server.log"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  PYTHON="$HOME/.local/mlx-server/bin/python3"
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  PYTHON="/opt/homebrew/bin/python3.12"
fi

if ! /usr/sbin/lsof -i "tcp:$PORT" >/dev/null 2>&1; then
  mkdir -p "$ROOT/dashboard/logs"
  /usr/bin/screen -dmS claude-stack-dashboard /bin/bash -lc \
    "cd '$ROOT' && CLAUDE_DASHBOARD_HOST=0.0.0.0 '$PYTHON' '$ROOT/dashboard/server.py' >> '$LOG' 2>&1"
fi

sleep 1
open "http://127.0.0.1:$PORT"
