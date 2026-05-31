from __future__ import annotations

from burr.core import ApplicationBuilder, State, action


@action(reads=["raw_requirements"], writes=["structured_requirements", "status"])
def refine_requirements(state: State) -> tuple[dict, State]:
    normalized = " ".join(state["raw_requirements"].split())
    structured_requirements = {
        "summary": normalized,
        "validated": bool(normalized),
        "requirement_count": 1 if normalized else 0,
    }
    return (
        {"structured_requirements": structured_requirements},
        state.update(structured_requirements=structured_requirements, status="complete"),
    )


def build_requirements_app(raw_requirements: str) -> ApplicationBuilder:
    return (
        ApplicationBuilder()
        .with_actions(refine_requirements=refine_requirements)
        .with_entrypoint("refine_requirements")
        .with_state(raw_requirements=raw_requirements, status="initialized")
    )
