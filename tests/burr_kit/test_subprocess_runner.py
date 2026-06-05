from __future__ import annotations

from app.burr_kit.subprocess_runner import RunnerConfig, SubprocessRunner, render_command


def test_dry_run_does_not_execute() -> None:
    runner = SubprocessRunner(RunnerConfig(dry_run=True))
    result = runner.run("echo hello")
    assert result.exit_code == 0
    assert result.stdout.startswith("[DRY RUN]")


def test_run_captures_stdout_and_exit_code() -> None:
    runner = SubprocessRunner(RunnerConfig(timeout=5.0))
    result = runner.run("printf 'hi\\n'")
    assert result.exit_code == 0
    assert result.stdout.strip() == "hi"


def test_timeout_sets_negative_exit_code() -> None:
    runner = SubprocessRunner(RunnerConfig(timeout=0.2))
    result = runner.run("sleep 1")
    assert result.exit_code == -1
    assert "Timed out" in result.stderr


def test_env_allowlist_filters_environment(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_THING", "should-not-leak")
    monkeypatch.setenv("PATH_SAFE", "ok")
    runner = SubprocessRunner(
        RunnerConfig(
            timeout=5.0,
            env_allowlist=["PATH_SAFE"],
            extra_env={"EXTRA": "from-config"},
        )
    )
    result = runner.run("printenv SECRET_THING || echo MISSING; printenv EXTRA")
    assert "MISSING" in result.stdout
    assert "from-config" in result.stdout


def test_render_command_substitutes_placeholders() -> None:
    assert render_command("calc {op} {a} {b}", {"op": "add", "a": "1", "b": "2"}) == "calc add 1 2"
