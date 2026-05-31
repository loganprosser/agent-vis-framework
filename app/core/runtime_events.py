from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol


class RuntimeEventStore(Protocol):
    def append_event(
        self,
        run_id: str,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class RuntimeEventContext:
    run_id: str
    node_id: str


_runtime_event_context: ContextVar[RuntimeEventContext | None] = ContextVar(
    "runtime_event_context",
    default=None,
)


@contextmanager
def bind_runtime_event_context(run_id: str, node_id: str) -> Iterator[None]:
    token = _runtime_event_context.set(RuntimeEventContext(run_id=run_id, node_id=node_id))
    try:
        yield
    finally:
        _runtime_event_context.reset(token)


def get_runtime_event_context() -> RuntimeEventContext | None:
    return _runtime_event_context.get()


def safe_append_event(
    event_store: RuntimeEventStore | None,
    run_id: str | None,
    event_type: str,
    *,
    node_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Record observability data without making event storage part of execution correctness."""

    if event_store is None or not run_id:
        return
    try:
        event_store.append_event(run_id, event_type, node_id=node_id, payload=payload)
    except Exception:  # noqa: BLE001 - telemetry failures must not fail workflow execution.
        return
