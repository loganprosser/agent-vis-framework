"""Safe subprocess runner with timeout, env allowlist, and dry-run mode."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class RunResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration: float


@dataclass
class CoverageConfig:
    """Optional code-coverage wrapping for Python targets.

    When `enabled`, `SubprocessRunner` rewrites commands whose argv[0] is
    either a Python interpreter (`python`/`python3`/`pythonX.Y`) or a Python
    entry-point script (shebang contains "python", e.g. `cowsay`) to invoke
    `python -m coverage run --append --data-file=<data_file> [--source=<roots>]
    -- <resolved-exe> <rest>`. Non-Python commands pass through unchanged.

    When `python_module` is set, bare commands matching that module name
    (e.g. `cowsay`) are rewritten to `python -m <module>` before wrapping,
    enabling coverage of Python packages whose system entry point is not Python.
    """

    enabled: bool = False
    data_file: str = ""
    source_roots: list[str] = field(default_factory=list)
    python_module: str = ""


@dataclass
class RunnerConfig:
    timeout: float = 30.0
    cwd: str | None = None
    env_allowlist: list[str] = field(
        default_factory=lambda: [
            "PATH", "HOME", "LANG", "TERM",
            "VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME",
            "PYTHONDONTWRITEBYTECODE",
        ]
    )
    extra_env: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False
    coverage: CoverageConfig = field(default_factory=CoverageConfig)


_PY_RE = re.compile(r"^python(?:\d(?:\.\d+)?)?$")


def _is_python_entry_point(exe: str) -> bool:
    """Return True if exe resolves to a script with a Python shebang line."""
    resolved = shutil.which(exe)
    if not resolved:
        return False
    try:
        with open(resolved, "rb") as f:
            first_line = f.read(128).split(b"\n", 1)[0]
        return b"python" in first_line
    except OSError:
        return False


def _maybe_wrap_with_coverage(command: str, cov: CoverageConfig) -> str:
    """Rewrite python invocations and Python entry-point scripts to run under coverage.

    Handles three cases:
      - `python script.py args`  — argv[0] is a python interpreter
      - `python -m module args`  — argv[0] is python + -m flag → coverage run -m module
      - `cowsay args`            — argv[0] is a Python entry-point (shebang contains "python")
      - `cowsay args`            — argv[0] matches cov.python_module → rewrite to
                                    `python -m <module>` then wrap with coverage

    In all cases the command becomes:
      python -m coverage run --append --data-file=... [--source=...] [-- module | -m module] args
    """
    if not cov.enabled or not cov.data_file:
        return command
    try:
        argv = shlex.split(command)
    except ValueError:
        return command
    if not argv:
        return command

    is_py_interpreter = _PY_RE.match(os.path.basename(argv[0]))
    is_py_entrypoint = not is_py_interpreter and _is_python_entry_point(argv[0])
    is_python_module = (
        not is_py_interpreter
        and not is_py_entrypoint
        and cov.python_module
        and os.path.basename(argv[0]) == cov.python_module
    )

    if not is_py_interpreter and not is_py_entrypoint and not is_python_module:
        return command

    # Build the coverage prefix
    py = "python3" if shutil.which("python3") else "python"
    cov_argv = [py, "-m", "coverage", "run", "--append", f"--data-file={cov.data_file}"]
    for root in cov.source_roots:
        cov_argv.append(f"--source={root}")

    if is_python_module:
        # `cowsay args` → `python -m coverage run ... -m cowsay args`
        cov_argv.append("-m")
        cov_argv.append(cov.python_module)
        cov_argv.extend(argv[1:])
    elif is_py_interpreter and len(argv) >= 3 and argv[1] == "-m":
        # `python -m module args` → `python -m coverage run ... -m module args`
        cov_argv.append("-m")
        cov_argv.extend(argv[2:])
    elif is_py_entrypoint:
        # `cowsay args` → `python -m coverage run ... -- <resolved> args`
        resolved = shutil.which(argv[0]) or argv[0]
        cov_argv.append("--")
        cov_argv.append(resolved)
        cov_argv.extend(argv[1:])
    else:
        # `python script.py args` → `python -m coverage run ... -- script.py args`
        cov_argv.append("--")
        cov_argv.extend(argv[1:])

    return " ".join(shlex.quote(a) for a in cov_argv)


class SubprocessRunner:
    def __init__(self, config: RunnerConfig | None = None):
        self.config = config or RunnerConfig()

    def run(self, command: str) -> RunResult:
        if self.config.dry_run:
            return RunResult(
                command=command,
                stdout=f"[DRY RUN] {command}",
                stderr="",
                exit_code=0,
                duration=0.0,
            )

        # Optionally rewrite the command to run under `coverage`.
        command = _maybe_wrap_with_coverage(command, self.config.coverage)

        env = self._build_env()
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                cwd=self.config.cwd,
                env=env,
            )
            return RunResult(
                command=command,
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                duration=round(time.monotonic() - start, 3),
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                command=command,
                stdout="",
                stderr=f"Timed out after {self.config.timeout}s",
                exit_code=-1,
                duration=round(time.monotonic() - start, 3),
            )

    def _build_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in self.config.env_allowlist:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        env.update(self.config.extra_env)
        return env


def render_command(template: str, values: dict[str, str]) -> str:
    """Substitute {param} placeholders in a command template."""
    return template.format(**values)
