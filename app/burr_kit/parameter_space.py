"""Pydantic models for parameter space definitions."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class TestParameter(BaseModel):
    name: str
    values: list[str]
    description: str | None = None

    @model_validator(mode="after")
    def _validate_values(self) -> TestParameter:
        if not self.values:
            raise ValueError(f"Parameter '{self.name}' must have at least one value")
        return self


class TestConstraint(BaseModel):
    type: str = "conditional"
    rule: str
    description: str | None = None


class ParameterModel(BaseModel):
    parameters: list[TestParameter]
    constraints: list[TestConstraint] = Field(default_factory=list)
    coverage_level: int = Field(default=2, ge=1, le=6)

    @model_validator(mode="after")
    def _validate_params(self) -> ParameterModel:
        if not self.parameters:
            raise ValueError("At least one parameter is required")
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate parameter names: {names}")
        return self
