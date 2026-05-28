#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"

cd "$ROOT_DIR"

if [[ ! -f "$PID_FILE" ]]; then
  if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    echo "No .server.pid file found, but an app uvicorn process is running."
    pkill -f "uvicorn app.main:app"
    echo "Stopped."
    exit 0
  fi
  echo "No .server.pid file found. Server is already stopped."
  exit 0
fi

PID="$(cat "$PID_FILE")"

if kill -0 "$PID" 2>/dev/null; then
  echo "Stopping server PID $PID..."
  kill "$PID"
  sleep 1
  if kill -0 "$PID" 2>/dev/null; then
    echo "Server is still stopping; sending a stronger signal."
    kill -TERM "$PID" 2>/dev/null || true
  fi
  echo "Stopped."
else
  echo "Server process was not running."
fi

rm -f "$PID_FILE"
