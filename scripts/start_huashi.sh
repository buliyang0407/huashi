#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://127.0.0.1:8787"
PID_FILE="$ROOT_DIR/data/huashi.pid"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/huashi.log"

mkdir -p "$ROOT_DIR/data" "$LOG_DIR"
cd "$ROOT_DIR"

is_running() {
  /usr/bin/curl -fsS "$URL/api/apps" >/dev/null 2>&1
}

if is_running; then
  echo "画室已经在运行：$URL"
  /usr/bin/open "$URL"
  exit 0
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && /bin/kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "发现旧进程 $OLD_PID，但服务未响应，先停止它。"
    /bin/kill "$OLD_PID" >/dev/null 2>&1 || true
    sleep 1
  fi
fi

echo "正在启动画室..."
/usr/bin/nohup /usr/bin/env python3 -m huashi.server --host 127.0.0.1 --port 8787 --data data >>"$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"

for _ in {1..30}; do
  if is_running; then
    echo "画室已启动：$URL"
    echo "日志：$LOG_FILE"
    /usr/bin/open "$URL"
    exit 0
  fi
  sleep 0.5
done

echo "画室启动超时，请查看日志：$LOG_FILE"
exit 1
