"""Pydantic models for TestForge backend interfaces and logging."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationWarning(BaseModel):
    parameter: str
    message: str


class ValidationError_(BaseModel):
    """Validation error from a TestForge backend. Suffixed _ to avoid
    shadowing the builtin — import as ``from .backend import ValidationError_ as ValidationError``."""
    parameter: str | None = None
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError_] = Field(default_factory=list)
    warnings: list[ValidationWarning] = Field(default_factory=list)


class ToolFeature(BaseModel):
    name: str
    available: bool = True


class ToolStatus(BaseModel):
    installed: bool
    name: str
    version: str | None = None
    features: list[ToolFeature] = Field(default_factory=list)
    message: str = ""


class RequestLog(BaseModel):
    timestamp: str
    method: str
    endpoint: str | None = None
    request_body: dict | None = None
    response_body: dict | None = None
    duration_ms: int
    backend: str
