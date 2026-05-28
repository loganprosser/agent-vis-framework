from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ModelRequest(BaseModel):
    model: str
    system_prompt: str = ""
    messages: list[dict[str, str]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    text: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ModelProvider(ABC):
    def __init__(self, provider_id: str, default_model: str, config: dict[str, Any] | None = None) -> None:
        self.provider_id = provider_id
        self.default_model = default_model
        self.config = config or {}

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a model response behind a provider-neutral interface."""
