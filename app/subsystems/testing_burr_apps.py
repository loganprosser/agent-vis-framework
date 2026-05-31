from __future__ import annotations

from time import sleep

from burr.core import ApplicationBuilder, State, action

from app.subsystems.example_burr_app import build_example_app


def build_not_runnable():
    return object()


def build_built_example_app(message: str):
    return build_example_app(message).build()


@action(reads=["message"], writes=["status"])
def fail_after_start(state: State) -> tuple[dict, State]:
    raise RuntimeError(f"intentional failure for {state['message']}")


def build_failing_app(message: str) -> ApplicationBuilder:
    return (
        ApplicationBuilder()
        .with_actions(fail_after_start=fail_after_start)
        .with_entrypoint("fail_after_start")
        .with_state(message=message, status="initialized")
    )


@action(reads=["message"], writes=["status"])
def finish_slowly(state: State) -> tuple[dict, State]:
    sleep(0.05)
    return {}, state.update(status="complete")


def build_slow_app(message: str) -> ApplicationBuilder:
    return (
        ApplicationBuilder()
        .with_actions(finish_slowly=finish_slowly)
        .with_entrypoint("finish_slowly")
        .with_state(message=message, status="initialized")
    )
