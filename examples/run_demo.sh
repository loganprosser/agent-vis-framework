#!/usr/bin/env bash
#
# Interactive picker over the agent-vis demos.
#
# Wraps ``python -m examples.run`` with fzf-driven menus for demo + provider
# so you can prove the framework is wired correctly against a fresh model
# in one keystroke.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

DEMO=""
PROVIDER=""
INPUTS=""
PRESET=""
FORMAT="pretty"
NON_INTERACTIVE=false

usage() {
  cat <<'EOF'
Usage: ./examples/run_demo.sh [--demo NAME] [--provider ID]
                              [--inputs JSON] [--preset NAME]
                              [--format pretty|json] [--non-interactive]

Demos:
  research_assistant    M4 ReAct orchestrator
  burr_code_review      M2 burr_kit + M3 Mermaid viz
  combinatorial_calc    M2 testforge + SubprocessRunner (no LLM)
  hybrid_pipeline       M4 → M2 composition

Providers are read from configs/models.yaml (register with
./configure-model.sh). Pass --non-interactive to skip fzf prompts and
fail if any required option is missing.
EOF
}

need_fzf() {
  if ! command -v fzf >/dev/null 2>&1; then
    echo "fzf is required. Install with: brew install fzf" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) DEMO="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --inputs) INPUTS="$2"; shift 2 ;;
    --preset) PRESET="$2"; shift 2 ;;
    --format) FORMAT="$2"; shift 2 ;;
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "$DEMO" ]]; then
  if [[ "$NON_INTERACTIVE" == "true" ]]; then
    echo "--demo is required with --non-interactive" >&2
    exit 1
  fi
  need_fzf
  DEMO="$(printf 'combinatorial_calc\nresearch_assistant\nburr_code_review\nhybrid_pipeline\n' \
    | fzf --height=40% --layout=reverse --border --prompt="Demo > ")"
fi

if [[ -z "$PROVIDER" ]]; then
  if [[ "$NON_INTERACTIVE" != "true" ]]; then
    need_fzf
    PROVIDER_LIST="$("$PYTHON" -c "
import yaml, pathlib
data = yaml.safe_load(pathlib.Path('configs/models.yaml').read_text()) or {}
print('(workflow default)')
for p in data.get('providers', []) or []:
    print(p.get('id', ''))
")"
    PROVIDER="$(printf '%s\n' "$PROVIDER_LIST" | fzf --height=40% --layout=reverse --border --prompt="Provider > ")"
    if [[ "$PROVIDER" == "(workflow default)" ]]; then PROVIDER=""; fi
  fi
fi

ARGS=("$DEMO" --format "$FORMAT")
if [[ -n "$PROVIDER" ]]; then ARGS+=(--provider "$PROVIDER"); fi
if [[ -n "$INPUTS" ]]; then ARGS+=(--inputs "$INPUTS"); fi
if [[ -n "$PRESET" ]]; then ARGS+=(--preset "$PRESET"); fi

cd "$ROOT_DIR"
exec "$PYTHON" -m examples.run "${ARGS[@]}"
