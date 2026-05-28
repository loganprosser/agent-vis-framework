from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


COPY_DIRS = ["app", "configs", "examples", "frontend", "tests"]
COPY_FILES = [
    "README.md",
    "CODING_AGENT_GUIDE.md",
    "pyproject.toml",
    "start.sh",
    "stop.sh",
    "status.sh",
    ".gitignore",
]


def init_project(target: Path, force: bool = False) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target = target.resolve()
    if target.exists() and any(target.iterdir()) and not force:
        raise SystemExit(f"Target directory is not empty: {target}. Use --force to copy into it.")
    target.mkdir(parents=True, exist_ok=True)

    for directory in COPY_DIRS:
        source = repo_root / directory
        destination = target / directory
        if not source.exists():
            continue
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "node_modules", "dist", ".vite"),
        )

    for filename in COPY_FILES:
        source = repo_root / filename
        if source.exists():
            shutil.copy2(source, target / filename)

    (target / "PROJECT.md").write_text(
        """# Agentic Workflow Project

This project was initialized from `agentic-workflow-framework`.

Project-specific files live in:

- `configs/workflows/`
- `configs/models.yaml`
- `configs/tools.yaml`
- `configs/mcps.yaml`

Run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./start.sh
```
""",
        encoding="utf-8",
    )

    print(f"Initialized agentic workflow project at {target}")


def validate_project(config_dir: Path) -> None:
    from app.core.config_loader import ConfigLoader

    loader = ConfigLoader(config_dir)
    workflows = loader.list_workflows()
    for workflow_name in workflows:
        loader.load_workflow(workflow_name)
    loader.load_models()
    loader.load_tools()
    loader.load_mcps()
    print(f"Validated {len(workflows)} workflow(s) in {config_dir}")


def run_dev(config_dir: Path | None = None, host: str = "127.0.0.1", port: int = 8000) -> None:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    env = None
    if config_dir is not None:
        import os

        env = {**os.environ, "WORKFLOW_CONFIG_DIR": str(config_dir)}
    raise SystemExit(subprocess.call(command, env=env))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agentic-workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new config-driven workflow project.")
    init_parser.add_argument("target", type=Path)
    init_parser.add_argument("--force", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="Validate project config files.")
    validate_parser.add_argument("--config-dir", type=Path, default=Path("configs"))

    run_parser = subparsers.add_parser("run", help="Run the FastAPI workflow server.")
    run_parser.add_argument("--config-dir", type=Path)
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    if args.command == "init":
        init_project(args.target, args.force)
    elif args.command == "validate":
        validate_project(args.config_dir)
    elif args.command == "run":
        run_dev(args.config_dir, args.host, args.port)


if __name__ == "__main__":
    main()
