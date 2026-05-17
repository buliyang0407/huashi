#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/data/huashi.pid"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && /bin/kill -0 "$PID" >/dev/null 2>&1; then
    echo "正在停止画室进程 $PID..."
    /bin/kill "$PID"
    sleep 1
  fi
  /bin/rm -f "$PID_FILE"
fi

PIDS="$(/usr/bin/lsof -ti tcp:8787 2>/dev/null || true)"
if [[ -n "$PIDS" ]]; then
  echo "端口 8787 仍有进程，继续停止：$PIDS"
  echo "$PIDS" | /usr/bin/xargs /bin/kill >/dev/null 2>&1 || true
fi

echo "画室已停止。"
