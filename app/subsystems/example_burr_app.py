from __future__ import annotations

from burr.core import ApplicationBuilder, State, action


@action(reads=["message"], writes=["greeting", "status"])
def greet(state: State) -> tuple[dict, State]:
    greeting = f"Hello, {state['message']}!"
    return {"greeting": greeting}, state.update(greeting=greeting, status="complete")


def build_example_app(message: str) -> ApplicationBuilder:
    return (
        ApplicationBuilder()
        .with_actions(greet=greet)
        .with_entrypoint("greet")
        .with_state(message=message, status="initialized")
    )
