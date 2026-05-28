#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"
LOG_FILE="$ROOT_DIR/.server.log"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-false}"

cd "$ROOT_DIR"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Server is already running."
    echo "URL: http://$HOST:$PORT/"
    echo "PID: $PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
  echo "Local virtualenv is missing dependencies. Installing now..."
  python3 -m venv "$ROOT_DIR/.venv"
  "$ROOT_DIR/.venv/bin/python" -m pip install -e ".[dev]"
fi

echo "Starting Agentic Workflow Editor..."
UVICORN_ARGS=(app.main:app --host "$HOST" --port "$PORT")
if [[ "$RELOAD" == "true" ]]; then
  UVICORN_ARGS+=(--reload)
fi

nohup "$ROOT_DIR/.venv/bin/uvicorn" "${UVICORN_ARGS[@]}" > "$LOG_FILE" 2>&1 &

PID="$!"
echo "$PID" > "$PID_FILE"

sleep 1

if kill -0 "$PID" 2>/dev/null; then
  echo "Started."
  echo "URL: http://$HOST:$PORT/"
  echo "API docs: http://$HOST:$PORT/docs"
  echo "PID: $PID"
  echo "Logs: $LOG_FILE"
else
  echo "Server failed to start. Last log lines:"
  tail -n 40 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi
