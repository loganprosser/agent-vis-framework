from __future__ import annotations

from burr.core import ApplicationBuilder, State, action, default, when

MIN_REQUIREMENTS_LENGTH = 12


@action(reads=["raw_requirements"], writes=["repair_happened", "status"])
def validate_requirements(state: State) -> tuple[dict, State]:
    normalized = " ".join(state["raw_requirements"].split())
    repair_required = len(normalized) < MIN_REQUIREMENTS_LENGTH
    status = "repair_required" if repair_required else "valid"
    return (
        {"repair_required": repair_required},
        state.update(repair_happened=False, status=status),
    )


@action(reads=["raw_requirements"], writes=["raw_requirements", "repair_happened", "status"])
def repair_requirements(state: State) -> tuple[dict, State]:
    normalized = " ".join(state["raw_requirements"].split())
    repaired_requirements = (
        f"{normalized} with sufficient implementation detail."
        if normalized
        else "Define clarified user requirements with sufficient implementation detail."
    )
    return (
        {"repaired_requirements": repaired_requirements},
        state.update(
            raw_requirements=repaired_requirements,
            repair_happened=True,
            status="repaired",
        ),
    )


@action(
    reads=["raw_requirements", "repair_happened"],
    writes=["structured_requirements", "validation_status", "status"],
)
def structure_requirements(state: State) -> tuple[dict, State]:
    normalized = " ".join(state["raw_requirements"].split())
    validation_status = "repaired" if state["repair_happened"] else "valid"
    structured_requirements = {
        "summary": normalized,
        "validated": True,
        "repair_happened": state["repair_happened"],
    }
    return (
        {
            "structured_requirements": structured_requirements,
            "validation_status": validation_status,
        },
        state.update(
            structured_requirements=structured_requirements,
            validation_status=validation_status,
            status="complete",
        ),
    )


def build_branching_requirements_app(raw_requirements: str) -> ApplicationBuilder:
    return (
        ApplicationBuilder()
        .with_actions(
            validate_requirements=validate_requirements,
            repair_requirements=repair_requirements,
            structure_requirements=structure_requirements,
        )
        .with_transitions(
            ("validate_requirements", "repair_requirements", when(status="repair_required")),
            ("validate_requirements", "structure_requirements", when(status="valid")),
            ("repair_requirements", "structure_requirements", default),
        )
        .with_entrypoint("validate_requirements")
        .with_state(raw_requirements=raw_requirements, status="initialized")
    )
