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

    litellm = subparsers.add_parser("litellm", help="Add or update a LiteLLM / OpenAI-compatible provider.")
    litellm.add_argument("--config-dir", default="configs")
    litellm.add_argument("--provider-id", default="litellm")
    litellm.add_argument("--model", required=True, help="Default model name or alias")
    litellm.add_argument("--base-url", default="http://localhost:4002/v1", help="OpenAI-compatible API base URL")
    litellm.add_argument("--api-key-env", default="LITELLM_API_KEY", help="Env var name holding the API key")
    litellm.add_argument("--temperature", type=float, default=0)

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

    elif args.command == "litellm":
        if not args.model.strip():
            raise SystemExit("--model must not be empty")
        if not args.base_url.strip():
            raise SystemExit("--base-url must not be empty")
        if not args.api_key_env.strip():
            raise SystemExit("--api-key-env must not be empty")
        provider = upsert_model_provider(
            Path(args.config_dir),
            provider_id=args.provider_id,
            provider_type="litellm",
            default_model=args.model,
            config={
                "base_url": args.base_url,
                "api_key_env": args.api_key_env,
                "temperature": args.temperature,
            },
        )
        print(f"Saved provider '{provider.id}' ({provider.type})")
        print(f"Default model: {provider.default_model}")
        print(f"Base URL: {provider.config['base_url']}")
        print(f"API key env: {provider.config['api_key_env']}")


if __name__ == "__main__":
    main()
