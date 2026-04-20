from __future__ import annotations

from typing import Any

from octopal.infrastructure.observability.base import TraceContext, new_span_id


class NoopTraceSink:
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
    ) -> TraceContext:
        del name, input, metadata
        return TraceContext(
            trace_id=trace_id,
            root_trace_id=root_trace_id,
            session_id=session_id,
            span_id=new_span_id(),
            chat_id=chat_id,
        )

    async def start_span(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        del name, metadata
        return TraceContext(
            trace_id=ctx.trace_id,
            root_trace_id=ctx.root_trace_id,
            session_id=ctx.session_id,
            span_id=new_span_id(),
            parent_span_id=ctx.span_id,
            chat_id=ctx.chat_id,
            worker_run_id=ctx.worker_run_id,
            lineage_id=ctx.lineage_id,
        )

    async def annotate(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        del ctx, name, metadata

    async def finish_span(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        del ctx, status, output, metadata

    async def finish_trace(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        del ctx, status, output, metadata
