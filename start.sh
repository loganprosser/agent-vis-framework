#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.server.pid"
LOG_FILE="$ROOT_DIR/.server.log"
FRONTEND_PID_FILE="$ROOT_DIR/.frontend.pid"
FRONTEND_LOG_FILE="$ROOT_DIR/.frontend.log"
RUNTIME_CONFIG_FILE="$ROOT_DIR/.runtime.env"
if [[ -f "$RUNTIME_CONFIG_FILE" ]]; then
  source "$RUNTIME_CONFIG_FILE"
fi
HOST="${HOST:-${CONFIG_HOST:-127.0.0.1}}"
PORT="${PORT:-${CONFIG_PORT:-8000}}"
FRONTEND_PORT="${FRONTEND_PORT:-${CONFIG_FRONTEND_PORT:-5173}}"
RELOAD="${RELOAD:-false}"
RUN_FRONTEND="${RUN_FRONTEND:-auto}"

cd "$ROOT_DIR"

listener_pid() {
  lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | sed -n '1p' || true
}

if [[ "$RUN_FRONTEND" != "false" && -f "$ROOT_DIR/frontend/package.json" ]] && command -v npm >/dev/null 2>&1; then
  TRACKED_FRONTEND_RUNNING=false
  if [[ -f "$FRONTEND_PID_FILE" ]]; then
    FRONTEND_PID="$(cat "$FRONTEND_PID_FILE")"
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
      TRACKED_FRONTEND_RUNNING=true
    fi
  fi
  if [[ "$TRACKED_FRONTEND_RUNNING" != "true" ]]; then
    FRONTEND_PORT_PID="$(listener_pid "$FRONTEND_PORT")"
    if [[ -n "$FRONTEND_PORT_PID" ]]; then
      echo "Cannot start React control plane: port $FRONTEND_PORT is already used by PID $FRONTEND_PORT_PID."
      ps -p "$FRONTEND_PORT_PID" -o command= || true
      echo "Stop that process or choose another port with FRONTEND_PORT=<port> ./start.sh."
      exit 1
    fi
  fi
fi

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Backend is already running."
    echo "API: http://$HOST:$PORT/"
    echo "Backend PID: $PID"
    BACKEND_RUNNING=true
  else
    rm -f "$PID_FILE"
  fi
fi

if [[ "${BACKEND_RUNNING:-false}" != "true" ]]; then
  PORT_PID="$(listener_pid "$PORT")"
  if [[ -n "$PORT_PID" ]]; then
    echo "Cannot start backend: port $PORT is already used by PID $PORT_PID."
    ps -p "$PORT_PID" -o command= || true
    exit 1
  fi

  if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
    echo "Local virtualenv is missing dependencies. Installing now..."
    python3 -m venv "$ROOT_DIR/.venv"
    "$ROOT_DIR/.venv/bin/python" -m pip install -e ".[dev]"
  fi

  echo "Starting backend..."
  UVICORN_ARGS=(app.main:app --host "$HOST" --port "$PORT")
  if [[ "$RELOAD" == "true" ]]; then
    UVICORN_ARGS+=(--reload)
  fi

  nohup "$ROOT_DIR/.venv/bin/uvicorn" "${UVICORN_ARGS[@]}" > "$LOG_FILE" 2>&1 &

  PID="$!"
  echo "$PID" > "$PID_FILE"

  sleep 1

  if kill -0 "$PID" 2>/dev/null; then
    echo "Backend started."
    echo "API: http://$HOST:$PORT/"
    echo "Backend PID: $PID"
    echo "Backend logs: $LOG_FILE"
  else
    echo "Backend failed to start. Last log lines:"
    tail -n 40 "$LOG_FILE" || true
    rm -f "$PID_FILE"
    exit 1
  fi
fi

if [[ "$RUN_FRONTEND" != "false" && -f "$ROOT_DIR/frontend/package.json" ]]; then
  if command -v npm >/dev/null 2>&1; then
    if [[ -f "$FRONTEND_PID_FILE" ]]; then
      FRONTEND_PID="$(cat "$FRONTEND_PID_FILE")"
      if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "React control plane already running: http://$HOST:$FRONTEND_PORT/"
        echo "Frontend PID: $FRONTEND_PID"
        echo "No-build fallback editor: http://$HOST:$PORT/"
        echo "API docs: http://$HOST:$PORT/docs"
        exit 0
      fi
      rm -f "$FRONTEND_PID_FILE"
    fi
    if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
      echo "Installing frontend dependencies..."
      (cd "$ROOT_DIR/frontend" && npm install)
    fi
    FRONTEND_PORT_PID="$(listener_pid "$FRONTEND_PORT")"
    if [[ -n "$FRONTEND_PORT_PID" ]]; then
      echo "Cannot start React control plane: port $FRONTEND_PORT is already used by PID $FRONTEND_PORT_PID."
      ps -p "$FRONTEND_PORT_PID" -o command= || true
      echo "Stop that process or choose another port with FRONTEND_PORT=<port> ./start.sh."
      exit 1
    fi
    echo "Starting React Flow control plane..."
    (
      cd "$ROOT_DIR/frontend"
      AGENTIC_WORKFLOW_API_PROXY="http://$HOST:$PORT" FRONTEND_PORT="$FRONTEND_PORT" nohup "$ROOT_DIR/frontend/node_modules/.bin/vite" --host "$HOST" --port "$FRONTEND_PORT" --strictPort > "$FRONTEND_LOG_FILE" 2>&1 &
      echo "$!" > "$FRONTEND_PID_FILE"
    )
    sleep 1
    FRONTEND_PID="$(cat "$FRONTEND_PID_FILE")"
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
      echo "Primary control plane: http://$HOST:$FRONTEND_PORT/"
      echo "Frontend PID: $FRONTEND_PID"
      echo "Frontend logs: $FRONTEND_LOG_FILE"
    else
      echo "React control plane failed to start. Last log lines:"
      tail -n 40 "$FRONTEND_LOG_FILE" || true
      rm -f "$FRONTEND_PID_FILE"
      exit 1
    fi
  elif [[ "$RUN_FRONTEND" == "true" ]]; then
    echo "RUN_FRONTEND=true was requested, but npm is not installed."
    exit 1
  else
    echo "npm not found; using embedded editor at http://$HOST:$PORT/"
  fi
fi

echo "No-build fallback editor: http://$HOST:$PORT/"
echo "API docs: http://$HOST:$PORT/docs"
