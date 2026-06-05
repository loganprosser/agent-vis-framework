"""TestForge client protocol — structural interface for all backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.burr_kit.testforge.backend_schemas import ToolStatus, ValidationResult
from app.burr_kit.parameter_space import ParameterModel
from app.burr_kit.testforge.test_case_schemas import TestGenerationResult


@runtime_checkable
class TestForgeClient(Protocol):
    """Interface that every TestForge backend must implement."""

    def validate_model(self, model: ParameterModel) -> ValidationResult: ...
    def generate_test_suite(self, model: ParameterModel) -> TestGenerationResult: ...
    def check_installation(self) -> ToolStatus: ...
