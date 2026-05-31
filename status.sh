#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"
FRONTEND_PID_FILE="$ROOT_DIR/.frontend.pid"
RUNTIME_CONFIG_FILE="$ROOT_DIR/.runtime.env"
if [[ -f "$RUNTIME_CONFIG_FILE" ]]; then
  source "$RUNTIME_CONFIG_FILE"
fi
HOST="${HOST:-${CONFIG_HOST:-127.0.0.1}}"
PORT="${PORT:-${CONFIG_PORT:-8000}}"
FRONTEND_PORT="${FRONTEND_PORT:-${CONFIG_FRONTEND_PORT:-5173}}"
FOUND=0
UNMANAGED=0

listener_pid() {
  lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | sed -n '1p' || true
}

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Backend is running."
    echo "API: http://$HOST:$PORT/"
    echo "No-build fallback editor: http://$HOST:$PORT/"
    echo "Backend PID: $PID"
    FOUND=1
  else
    rm -f "$PID_FILE"
  fi
fi

if [[ -f "$FRONTEND_PID_FILE" ]]; then
  FRONTEND_PID="$(cat "$FRONTEND_PID_FILE")"
  if kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "React control plane is running."
    echo "Primary control plane: http://$HOST:$FRONTEND_PORT/"
    echo "Frontend PID: $FRONTEND_PID"
    FOUND=1
  else
    rm -f "$FRONTEND_PID_FILE"
  fi
fi

if [[ ! -f "$PID_FILE" ]]; then
  PORT_PID="$(listener_pid "$PORT")"
  if [[ -n "$PORT_PID" ]]; then
    echo "Backend port $PORT is occupied by unmanaged PID $PORT_PID."
    UNMANAGED=1
  fi
fi

if [[ ! -f "$FRONTEND_PID_FILE" ]]; then
  FRONTEND_PORT_PID="$(listener_pid "$FRONTEND_PORT")"
  if [[ -n "$FRONTEND_PORT_PID" ]]; then
    echo "Frontend port $FRONTEND_PORT is occupied by unmanaged PID $FRONTEND_PORT_PID."
    UNMANAGED=1
  fi
fi

if [[ "$FOUND" == "1" ]]; then
  exit 0
fi

if [[ "$UNMANAGED" == "1" ]]; then
  echo "This workspace has no matching managed PID files."
  exit 1
fi

echo "Backend and React control plane are not running."
exit 1
