from __future__ import annotations

import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    root_trace_id: str
    session_id: str
    span_id: str
    parent_span_id: str | None = None
    chat_id: int | None = None
    worker_run_id: str | None = None
    lineage_id: str | None = None


class TraceSink(Protocol):
    async def start_trace(
        self,
        *,
        name: str,
        trace_id: str,
        root_trace_id: str,
        session_id: str,
        chat_id: int | None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext: ...

    async def start_span(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext: ...

    async def annotate(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def finish_span(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def finish_trace(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


_current_trace_context: ContextVar[TraceContext | None] = ContextVar(
    "octopal_observability_trace_context",
    default=None,
)


def get_current_trace_context() -> TraceContext | None:
    return _current_trace_context.get()


def bind_trace_context(ctx: TraceContext | None) -> Token[TraceContext | None]:
    return _current_trace_context.set(ctx)


def reset_trace_context(token: Token[TraceContext | None]) -> None:
    _current_trace_context.reset(token)


def new_span_id() -> str:
    return uuid4().hex


def now_ms() -> float:
    return time.perf_counter() * 1000.0
