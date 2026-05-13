from __future__ import annotations

from typing import Any
from uuid import uuid4

from octopal.infrastructure.observability.base import (
    TraceSink,
    bind_trace_context,
    get_current_trace_context,
    reset_trace_context,
)


async def _start_background_trace_context(
    trace_sink: TraceSink | None,
    *,
    name: str,
    chat_id: int,
    correlation_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> tuple[Any | None, Any | None, bool]:
    if trace_sink is None:
        return None, None, False
    parent_trace_ctx = get_current_trace_context()
    if parent_trace_ctx is not None:
        trace_ctx = await trace_sink.start_span(
            parent_trace_ctx,
            name=name,
            metadata=metadata,
        )
        return trace_ctx, bind_trace_context(trace_ctx), False
    trace_id = f"{name.replace('.', '-')}-{uuid4().hex}"
    root_trace_id = str(correlation_id or trace_id)
    trace_ctx = await trace_sink.start_trace(
        name=name,
        trace_id=trace_id,
        root_trace_id=root_trace_id,
        session_id=f"chat:{chat_id}",
        chat_id=chat_id,
        metadata=metadata,
    )
    return trace_ctx, bind_trace_context(trace_ctx), True


async def _finish_background_trace_context(
    trace_sink: TraceSink | None,
    trace_ctx: Any | None,
    trace_token: Any | None,
    *,
    is_root_trace: bool,
    status: str,
    output: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> None:
    try:
        if trace_ctx is None or trace_sink is None:
            return
        if is_root_trace:
            await trace_sink.finish_trace(
                trace_ctx,
                status=status,
                output=output,
                metadata=metadata,
            )
            return
        await trace_sink.finish_span(
            trace_ctx,
            status=status,
            output=output,
            metadata=metadata,
        )
    finally:
        if trace_token is not None:
            reset_trace_context(trace_token)
