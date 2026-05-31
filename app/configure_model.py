from __future__ import annotations

import argparse
from pathlib import Path

from app.core.model_config import upsert_model_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persist model provider configuration.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ollama = subparsers.add_parser("ollama", help="Add or update a native Ollama provider.")
    ollama.add_argument("--config-dir", default="configs")
    ollama.add_argument("--provider-id", default="ollama_local")
    ollama.add_argument("--model", required=True)
    ollama.add_argument("--context-length", type=int, required=True)
    ollama.add_argument("--base-url", default="http://127.0.0.1:11434")
    ollama.add_argument("--temperature", type=float, default=0)
    ollama.add_argument("--timeout-seconds", type=float, default=120)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "ollama":
        if args.context_length <= 0:
            raise SystemExit("--context-length must be greater than zero")
        provider = upsert_model_provider(
            Path(args.config_dir),
            provider_id=args.provider_id,
            provider_type="ollama",
            default_model=args.model,
            config={
                "base_url": args.base_url,
                "context_length": args.context_length,
                "temperature": args.temperature,
                "timeout_seconds": args.timeout_seconds,
            },
        )
        print(f"Saved provider '{provider.id}' ({provider.type})")
        print(f"Default model: {provider.default_model}")
        print(f"Context length: {provider.config['context_length']}")


if __name__ == "__main__":
    main()
