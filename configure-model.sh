#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$ROOT_DIR/configs"
PROVIDER=""
PROVIDER_ID=""
MODEL=""
CONTEXT_LENGTH=""
OLLAMA_BASE_URL_DEFAULT="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
LITELLM_BASE_URL_DEFAULT="${LITELLM_BASE_URL:-http://127.0.0.1:4000/v1}"
BASE_URL=""
API_KEY_ENV=""
RITS_HEADER_ENV=""
RITS_CATALOG_DEFAULT="$CONFIG_DIR/providers/rits/models.json"
NON_INTERACTIVE=false

usage() {
  cat <<'EOF'
Usage: ./configure-model [options]

Configure a model provider in configs/models.yaml. Interactive selections use fzf.

Provider types:
  ollama   Native Ollama HTTP API
  litellm  Any OpenAI-compatible LiteLLM proxy
  rits     IBM RITS-hosted model behind a LiteLLM proxy

Options:
  --provider PROVIDER         ollama | litellm | rits
  --provider-id ID            Saved provider id (default depends on provider)
  --model MODEL               Model name to persist
  --context-length TOKENS     Context window (ollama only)
  --base-url URL              Override base URL
  --api-key-env VAR           Env var holding the bearer token (litellm/rits)
  --rits-header-env VAR       Env var for the RITS_API_KEY header (rits only)
  --config-dir PATH           Config directory, default: ./configs
  --non-interactive           Require all values upfront
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
    --provider) PROVIDER="$2"; shift 2 ;;
    --provider-id) PROVIDER_ID="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --context-length) CONTEXT_LENGTH="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --api-key-env) API_KEY_ENV="$2"; shift 2 ;;
    --rits-header-env) RITS_HEADER_ENV="$2"; shift 2 ;;
    --config-dir) CONFIG_DIR="$2"; shift 2 ;;
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
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
  PROVIDER="$(printf 'ollama\nlitellm\nrits\n' | select_with_fzf "Provider > ")"
fi

case "$PROVIDER" in
  ollama|litellm|rits) ;;
  *) echo "Unsupported provider: $PROVIDER. Choose ollama | litellm | rits." >&2; exit 1 ;;
esac

# Per-provider defaults for provider-id.
if [[ -z "$PROVIDER_ID" ]]; then
  case "$PROVIDER" in
    ollama)  PROVIDER_ID="ollama_local" ;;
    litellm) PROVIDER_ID="litellm_proxy" ;;
    rits)    PROVIDER_ID="rits_default" ;;
  esac
fi

if [[ "$PROVIDER" == "ollama" ]]; then
  if [[ -z "$BASE_URL" ]]; then BASE_URL="$OLLAMA_BASE_URL_DEFAULT"; fi
  if [[ -z "$MODEL" ]]; then
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
      echo "--model is required with --non-interactive" >&2; exit 1
    fi
    MODEL_LIST="$(curl --fail --silent --show-error --max-time 5 "$BASE_URL/api/tags" \
      | "$PYTHON" -c 'import json, sys; print("\n".join(m["name"] for m in json.load(sys.stdin).get("models", [])))')"
    if [[ -z "$MODEL_LIST" ]]; then
      echo "No Ollama models found at $BASE_URL. Install one with: ollama pull <model>" >&2
      exit 1
    fi
    MODEL="$(printf '%s\n' "$MODEL_LIST" | select_with_fzf "Ollama model > ")"
  fi
  if [[ -z "$CONTEXT_LENGTH" ]]; then
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
      echo "--context-length is required with --non-interactive" >&2; exit 1
    fi
    CONTEXT_CHOICE="$(printf '%s\n' \
      '4096    Compact' '8192    Balanced' '16384   Extended' \
      '32768   Large' '65536   Very large' 'custom  Enter another value' \
      | select_with_fzf "Context tokens > ")"
    CONTEXT_LENGTH="${CONTEXT_CHOICE%% *}"
    if [[ "$CONTEXT_LENGTH" == "custom" ]]; then
      read -r -p "Context length in tokens: " CONTEXT_LENGTH
    fi
  fi
  if [[ ! "$CONTEXT_LENGTH" =~ ^[0-9]+$ ]] || (( CONTEXT_LENGTH < 1 )); then
    echo "Context length must be a positive integer: $CONTEXT_LENGTH" >&2; exit 1
  fi
  cd "$ROOT_DIR"
  "$PYTHON" -m app.configure_model ollama \
    --config-dir "$CONFIG_DIR" --provider-id "$PROVIDER_ID" --model "$MODEL" \
    --context-length "$CONTEXT_LENGTH" --base-url "$BASE_URL"

elif [[ "$PROVIDER" == "litellm" ]]; then
  if [[ -z "$BASE_URL" ]]; then BASE_URL="$LITELLM_BASE_URL_DEFAULT"; fi
  if [[ -z "$API_KEY_ENV" ]]; then API_KEY_ENV="LITELLM_API_KEY"; fi
  if [[ -z "$MODEL" ]]; then
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
      echo "--model is required with --non-interactive" >&2; exit 1
    fi
    MODEL_LIST="$(curl --fail --silent --show-error --max-time 5 "$BASE_URL/models" \
      | "$PYTHON" -c 'import json, sys
data = json.load(sys.stdin)
items = data.get("data") if isinstance(data, dict) else data
for item in items or []:
    print(item.get("id") if isinstance(item, dict) else item)
' 2>/dev/null || true)"
    if [[ -n "$MODEL_LIST" ]]; then
      MODEL="$(printf '%s\n' "$MODEL_LIST" | select_with_fzf "LiteLLM model > ")"
    else
      read -r -p "Model name: " MODEL
    fi
  fi
  cd "$ROOT_DIR"
  "$PYTHON" -m app.configure_model litellm \
    --config-dir "$CONFIG_DIR" --provider-id "$PROVIDER_ID" --model "$MODEL" \
    --base-url "$BASE_URL" --api-key-env "$API_KEY_ENV"

elif [[ "$PROVIDER" == "rits" ]]; then
  if [[ -z "$BASE_URL" ]]; then BASE_URL="$LITELLM_BASE_URL_DEFAULT"; fi
  if [[ -z "$API_KEY_ENV" ]]; then API_KEY_ENV="RITS_API_KEY"; fi
  if [[ -z "$RITS_HEADER_ENV" ]]; then RITS_HEADER_ENV="RITS_API_KEY"; fi
  if [[ -z "$MODEL" ]]; then
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
      echo "--model is required with --non-interactive" >&2; exit 1
    fi
    # Prefer the locally-scraped RITS catalog if present.
    MODEL_LIST=""
    if [[ -f "$RITS_CATALOG_DEFAULT" ]]; then
      MODEL_LIST="$("$PYTHON" -c '
import json, sys, pathlib
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
items = data if isinstance(data, list) else data.get("models", [])
for m in items:
    name = m.get("model_name") or m.get("name") or m.get("id")
    if name: print(name)
' "$RITS_CATALOG_DEFAULT" 2>/dev/null || true)"
    fi
    if [[ -n "$MODEL_LIST" ]]; then
      MODEL="$(printf '%s\n' "$MODEL_LIST" | select_with_fzf "RITS model > ")"
    else
      echo "No RITS catalog found at $RITS_CATALOG_DEFAULT." >&2
      echo "Run: $PYTHON scripts/providers/rits/scrape_rits_models.py to populate it." >&2
      read -r -p "Model name: " MODEL
    fi
  fi
  cd "$ROOT_DIR"
  "$PYTHON" -m app.configure_model rits \
    --config-dir "$CONFIG_DIR" --provider-id "$PROVIDER_ID" --model "$MODEL" \
    --base-url "$BASE_URL" --api-key-env "$API_KEY_ENV" --rits-header-env "$RITS_HEADER_ENV"
fi

echo
echo "Provider '$PROVIDER_ID' ($PROVIDER) is ready."
echo "Select it on workflow nodes in the React control plane, or set provider: $PROVIDER_ID in workflow YAML."
