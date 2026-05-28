#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"
LOG_FILE="$ROOT_DIR/.server.log"
FRONTEND_PID_FILE="$ROOT_DIR/.frontend.pid"
FRONTEND_LOG_FILE="$ROOT_DIR/.frontend.log"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
RELOAD="${RELOAD:-false}"
RUN_FRONTEND="${RUN_FRONTEND:-auto}"

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
  echo "Embedded editor: http://$HOST:$PORT/"
  echo "API docs: http://$HOST:$PORT/docs"
  echo "PID: $PID"
  echo "Logs: $LOG_FILE"
else
  echo "Server failed to start. Last log lines:"
  tail -n 40 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

if [[ "$RUN_FRONTEND" != "false" && -f "$ROOT_DIR/frontend/package.json" ]]; then
  if command -v npm >/dev/null 2>&1; then
    if [[ -f "$FRONTEND_PID_FILE" ]]; then
      FRONTEND_PID="$(cat "$FRONTEND_PID_FILE")"
      if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "React editor already running: http://$HOST:$FRONTEND_PORT/"
        exit 0
      fi
      rm -f "$FRONTEND_PID_FILE"
    fi
    if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
      echo "Installing frontend dependencies..."
      (cd "$ROOT_DIR/frontend" && npm install)
    fi
    echo "Starting React Flow editor..."
    (
      cd "$ROOT_DIR/frontend"
      AGENTIC_WORKFLOW_API_PROXY="http://$HOST:$PORT" FRONTEND_PORT="$FRONTEND_PORT" nohup npm run dev -- --port "$FRONTEND_PORT" > "$FRONTEND_LOG_FILE" 2>&1 &
      echo "$!" > "$FRONTEND_PID_FILE"
    )
    echo "React editor: http://$HOST:$FRONTEND_PORT/"
    echo "Frontend logs: $FRONTEND_LOG_FILE"
  elif [[ "$RUN_FRONTEND" == "true" ]]; then
    echo "RUN_FRONTEND=true was requested, but npm is not installed."
    exit 1
  else
    echo "npm not found; using embedded editor at http://$HOST:$PORT/"
  fi
fi
