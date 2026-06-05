from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

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

    litellm = subparsers.add_parser(
        "litellm", help="Add or update an OpenAI-compatible LiteLLM provider."
    )
    litellm.add_argument("--config-dir", default="configs")
    litellm.add_argument("--provider-id", default="litellm_proxy")
    litellm.add_argument("--model", required=True)
    litellm.add_argument("--base-url", default="http://127.0.0.1:4000/v1")
    litellm.add_argument("--api-key-env", default="LITELLM_API_KEY")
    litellm.add_argument("--temperature", type=float, default=0)

    rits = subparsers.add_parser(
        "rits", help="Add or update an IBM RITS provider (via LiteLLM proxy)."
    )
    rits.add_argument("--config-dir", default="configs")
    rits.add_argument("--provider-id", default="rits_default")
    rits.add_argument(
        "--model",
        required=True,
        help="Model name as exposed by the LiteLLM proxy (e.g. GLM-5.1-FP8).",
    )
    rits.add_argument(
        "--base-url",
        default="http://127.0.0.1:4000/v1",
        help="OpenAI-compatible base URL of the LiteLLM proxy.",
    )
    rits.add_argument(
        "--api-key-env",
        default="RITS_API_KEY",
        help="Env var that holds the OpenAI Authorization token.",
    )
    rits.add_argument(
        "--rits-header-env",
        default="RITS_API_KEY",
        help="Env var whose value is sent as the RITS_API_KEY header.",
    )
    rits.add_argument("--temperature", type=float, default=0)

    return parser


def _save(
    config_dir: str,
    provider_id: str,
    provider_type: str,
    default_model: str,
    config: dict[str, Any],
) -> None:
    provider = upsert_model_provider(
        Path(config_dir),
        provider_id=provider_id,
        provider_type=provider_type,
        default_model=default_model,
        config=config,
    )
    print(f"Saved provider '{provider.id}' ({provider.type})")
    print(f"Default model: {provider.default_model}")


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "ollama":
        if args.context_length <= 0:
            raise SystemExit("--context-length must be greater than zero")
        _save(
            args.config_dir,
            args.provider_id,
            "ollama",
            args.model,
            {
                "base_url": args.base_url,
                "context_length": args.context_length,
                "temperature": args.temperature,
                "timeout_seconds": args.timeout_seconds,
            },
        )
    elif args.command == "litellm":
        _save(
            args.config_dir,
            args.provider_id,
            "litellm",
            args.model,
            {
                "base_url": args.base_url,
                "api_key_env": args.api_key_env,
                "temperature": args.temperature,
            },
        )
    elif args.command == "rits":
        _save(
            args.config_dir,
            args.provider_id,
            "rits",
            args.model,
            {
                "base_url": args.base_url,
                "api_key_env": args.api_key_env,
                "rits_header_env": args.rits_header_env,
                "temperature": args.temperature,
            },
        )


if __name__ == "__main__":
    main()
