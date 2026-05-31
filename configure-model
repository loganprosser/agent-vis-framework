#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$ROOT_DIR/configs"
PROVIDER=""
PROVIDER_ID="ollama_local"
MODEL=""
CONTEXT_LENGTH=""
BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
NON_INTERACTIVE=false

usage() {
  cat <<'EOF'
Usage: ./configure-model [options]

Configure a model provider in configs/models.yaml. Interactive selections use fzf.
Only the native Ollama provider is available in this first version.

Options:
  --provider PROVIDER         Provider type, currently: ollama
  --provider-id ID            Saved provider id, default: ollama_local
  --model MODEL               Installed Ollama model name
  --context-length TOKENS     Context window in tokens
  --base-url URL              Ollama API URL, default: http://127.0.0.1:11434
  --config-dir PATH           Config directory, default: ./configs
  --non-interactive           Require explicit provider, model, and context values
  -h, --help                  Show this help
EOF
}

select_with_fzf() {
  local prompt="$1"
  fzf --height=40% --layout=reverse --border --prompt="$prompt"
}

need_fzf() {
  if ! command -v fzf >/dev/null 2>&1; then
    echo "fzf is required for interactive model configuration. Install it with: brew install fzf" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      PROVIDER="$2"
      shift 2
      ;;
    --provider-id)
      PROVIDER_ID="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --context-length)
      CONTEXT_LENGTH="$2"
      shift 2
      ;;
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --config-dir)
      CONFIG_DIR="$2"
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

PYTHON="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

if [[ "$NON_INTERACTIVE" != "true" ]]; then
  need_fzf
fi

if [[ -z "$PROVIDER" ]]; then
  if [[ "$NON_INTERACTIVE" == "true" ]]; then
    echo "--provider is required with --non-interactive" >&2
    exit 1
  fi
  PROVIDER="$(printf 'ollama\n' | select_with_fzf "Provider > ")"
fi

if [[ "$PROVIDER" != "ollama" ]]; then
  echo "Unsupported provider: $PROVIDER. Available providers: ollama" >&2
  exit 1
fi

if [[ -z "$MODEL" ]]; then
  if [[ "$NON_INTERACTIVE" == "true" ]]; then
    echo "--model is required with --non-interactive" >&2
    exit 1
  fi
  MODEL_LIST="$(
    curl --fail --silent --show-error --max-time 5 "$BASE_URL/api/tags" \
      | "$PYTHON" -c 'import json, sys; print("\n".join(model["name"] for model in json.load(sys.stdin).get("models", [])))'
  )"
  if [[ -z "$MODEL_LIST" ]]; then
    echo "No Ollama models found at $BASE_URL. Install one with: ollama pull <model>" >&2
    exit 1
  fi
  MODEL="$(printf '%s\n' "$MODEL_LIST" | select_with_fzf "Ollama model > ")"
fi

if [[ -z "$CONTEXT_LENGTH" ]]; then
  if [[ "$NON_INTERACTIVE" == "true" ]]; then
    echo "--context-length is required with --non-interactive" >&2
    exit 1
  fi
  CONTEXT_CHOICE="$(
    printf '%s\n' \
      '4096    Compact' \
      '8192    Balanced' \
      '16384   Extended' \
      '32768   Large' \
      '65536   Very large' \
      'custom  Enter another value' \
      | select_with_fzf "Context tokens > "
  )"
  CONTEXT_LENGTH="${CONTEXT_CHOICE%% *}"
  if [[ "$CONTEXT_LENGTH" == "custom" ]]; then
    read -r -p "Context length in tokens: " CONTEXT_LENGTH
  fi
fi

if [[ ! "$CONTEXT_LENGTH" =~ ^[0-9]+$ ]] || (( CONTEXT_LENGTH < 1 )); then
  echo "Context length must be a positive integer: $CONTEXT_LENGTH" >&2
  exit 1
fi

cd "$ROOT_DIR"
"$PYTHON" -m app.configure_model ollama \
  --config-dir "$CONFIG_DIR" \
  --provider-id "$PROVIDER_ID" \
  --model "$MODEL" \
  --context-length "$CONTEXT_LENGTH" \
  --base-url "$BASE_URL"

echo
echo "Ollama provider '$PROVIDER_ID' is ready."
echo "Select it on workflow nodes in the React control plane, or set provider: $PROVIDER_ID in workflow YAML."
