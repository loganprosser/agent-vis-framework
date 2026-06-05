"""Pydantic models for test cases and execution records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    id: int
    values: dict[str, str]


class CoverageReport(BaseModel):
    total_combinations: int
    generated_tests: int
    reduction_percentage: float
    coverage_level: int
    parameter_coverage: dict[str, float] = Field(default_factory=dict)


class ExecutionRecord(BaseModel):
    test_id: int
    rendered_command: str
    stdout: str
    stderr: str
    exit_code: int
    duration: float


class TestGenerationResult(BaseModel):
    test_cases: list[TestCase]
    coverage: CoverageReport
    execution_time: int
    warning: str | None = None
