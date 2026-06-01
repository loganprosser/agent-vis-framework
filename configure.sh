#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$ROOT_DIR/.runtime.env"
HOST_VALUE=""
PORT_VALUE=""
FRONTEND_PORT_VALUE=""
NON_INTERACTIVE=false

usage() {
  cat <<'EOF'
Usage: ./configure [options]

Configure persisted ports for ./start.sh and ./status.sh.

Options:
  --host HOST                 Bind host, default: 127.0.0.1
  --backend-port PORT         FastAPI port, default: 8000
  --frontend-port PORT        React control plane port, default: 5173
  --config-file PATH          Write an alternate config file
  --non-interactive           Accept provided values and defaults without prompts
  -h, --help                  Show this help
EOF
}

validate_port() {
  local label="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value < 1 || value > 65535 )); then
    echo "$label must be an integer between 1 and 65535: $value" >&2
    exit 1
  fi
}

prompt_value() {
  local label="$1"
  local current="$2"
  local value=""
  read -r -p "$label [$current]: " value
  printf '%s' "${value:-$current}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST_VALUE="$2"
      shift 2
      ;;
    --backend-port)
      PORT_VALUE="$2"
      shift 2
      ;;
    --frontend-port)
      FRONTEND_PORT_VALUE="$2"
      shift 2
      ;;
    --config-file)
      CONFIG_FILE="$2"
      shift 2
      ;;
    --non-interactive)
      NON_INTERACTIVE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -f "$CONFIG_FILE" ]]; then
  source "$CONFIG_FILE"
fi

HOST_VALUE="${HOST_VALUE:-${CONFIG_HOST:-127.0.0.1}}"
PORT_VALUE="${PORT_VALUE:-${CONFIG_PORT:-8000}}"
FRONTEND_PORT_VALUE="${FRONTEND_PORT_VALUE:-${CONFIG_FRONTEND_PORT:-5173}}"

if [[ "$NON_INTERACTIVE" != "true" ]]; then
  HOST_VALUE="$(prompt_value "Bind host" "$HOST_VALUE")"
  PORT_VALUE="$(prompt_value "FastAPI backend port" "$PORT_VALUE")"
  FRONTEND_PORT_VALUE="$(prompt_value "React control plane port" "$FRONTEND_PORT_VALUE")"
fi

validate_port "Backend port" "$PORT_VALUE"
validate_port "Frontend port" "$FRONTEND_PORT_VALUE"
if [[ "$PORT_VALUE" == "$FRONTEND_PORT_VALUE" ]]; then
  echo "Backend and frontend ports must be different." >&2
  exit 1
fi

mkdir -p "$(dirname "$CONFIG_FILE")"
{
  printf 'CONFIG_HOST=%q\n' "$HOST_VALUE"
  printf 'CONFIG_PORT=%q\n' "$PORT_VALUE"
  printf 'CONFIG_FRONTEND_PORT=%q\n' "$FRONTEND_PORT_VALUE"
} > "$CONFIG_FILE"

echo "Saved runtime configuration: $CONFIG_FILE"
echo "Backend API:           http://$HOST_VALUE:$PORT_VALUE/"
echo "React control plane:   http://$HOST_VALUE:$FRONTEND_PORT_VALUE/"
echo "No-build fallback UI:  http://$HOST_VALUE:$PORT_VALUE/"
echo
echo "Run ./start.sh to start both services."
