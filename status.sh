#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"
FRONTEND_PID_FILE="$ROOT_DIR/.frontend.pid"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
FOUND=0

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Backend is running."
    echo "Embedded editor: http://$HOST:$PORT/"
    echo "PID: $PID"
    FOUND=1
  fi
fi

if [[ -f "$FRONTEND_PID_FILE" ]]; then
  FRONTEND_PID="$(cat "$FRONTEND_PID_FILE")"
  if kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "React editor is running."
    echo "URL: http://$HOST:$FRONTEND_PORT/"
    echo "PID: $FRONTEND_PID"
    FOUND=1
  fi
fi

if [[ "$FOUND" == "1" ]]; then
  exit 0
fi

echo "Server is not running."
exit 1
