from __future__ import annotations

from typing import Any

import structlog

from octopal.infrastructure.observability.base import TraceContext, new_span_id

logger = structlog.get_logger(__name__)


class LangfuseTraceSink:
    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str | None,
        sample_rate: float,
        tracing_enabled: bool = True,
    ) -> None:
        from langfuse.otel import Langfuse

        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            sample_rate=sample_rate,
            tracing_enabled=tracing_enabled,
        )
        self._active_handles: dict[str, tuple[Any, Any]] = {}

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
        ctx = TraceContext(
            trace_id=trace_id,
            root_trace_id=root_trace_id,
            session_id=session_id,
            span_id=new_span_id(),
            chat_id=chat_id,
        )
        payload = dict(metadata or {})
        payload.setdefault("app_trace_id", trace_id)
        payload.setdefault("root_trace_id", root_trace_id)
        payload.setdefault("session_id", session_id)
        if chat_id is not None:
            payload.setdefault("chat_id", chat_id)
        self._enter_observation(
            ctx.span_id,
            name=name,
            input=input,
            metadata=payload,
        )
        return ctx

    async def start_span(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        child = TraceContext(
            trace_id=ctx.trace_id,
            root_trace_id=ctx.root_trace_id,
            session_id=ctx.session_id,
            span_id=new_span_id(),
            parent_span_id=ctx.span_id,
            chat_id=ctx.chat_id,
            worker_run_id=ctx.worker_run_id,
            lineage_id=ctx.lineage_id,
        )
        payload = dict(metadata or {})
        payload.setdefault("app_trace_id", ctx.trace_id)
        payload.setdefault("root_trace_id", ctx.root_trace_id)
        payload.setdefault("session_id", ctx.session_id)
        if ctx.chat_id is not None:
            payload.setdefault("chat_id", ctx.chat_id)
        if ctx.worker_run_id:
            payload.setdefault("worker_run_id", ctx.worker_run_id)
        if ctx.lineage_id:
            payload.setdefault("lineage_id", ctx.lineage_id)
        self._enter_observation(
            child.span_id,
            name=name,
            metadata=payload,
            as_type=_observation_type_for_name(name),
        )
        return child

    async def annotate(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        handle = self._active_handles.get(ctx.span_id)
        if handle is None:
            return
        _, observation = handle
        try:
            update_payload = {"last_annotation": name}
            if metadata:
                update_payload["annotation"] = metadata
            observation.update(metadata=update_payload)
        except Exception:
            logger.debug("Langfuse annotate failed", span_id=ctx.span_id, exc_info=True)

    async def finish_span(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._close_observation(
            ctx.span_id,
            status=status,
            output=output,
            metadata=metadata,
        )

    async def finish_trace(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._close_observation(
            ctx.span_id,
            status=status,
            output=output,
            metadata=metadata,
        )

    def _enter_observation(
        self,
        span_id: str,
        *,
        name: str,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        as_type: str = "span",
    ) -> None:
        cm = self._client.start_as_current_observation(
            name=name,
            as_type=as_type,
            input=input,
            metadata=metadata,
        )
        observation = cm.__enter__()
        self._active_handles[span_id] = (cm, observation)

    def _close_observation(
        self,
        span_id: str,
        *,
        status: str,
        output: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        handle = self._active_handles.pop(span_id, None)
        if handle is None:
            return
        cm, observation = handle
        try:
            update_payload = dict(metadata or {})
            update_payload.setdefault("status", status)
            observation.update(
                output=output,
                metadata=update_payload or None,
                level="ERROR" if status == "error" else "DEFAULT",
                status_message=(
                    update_payload.get("error_message_short") if update_payload else None
                ),
            )
        except Exception:
            logger.debug("Langfuse observation update failed", span_id=span_id, exc_info=True)
        finally:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                logger.debug("Langfuse observation close failed", span_id=span_id, exc_info=True)


def _observation_type_for_name(name: str) -> str:
    if name == "llm.call":
        return "generation"
    if name == "octo.tool":
        return "tool"
    if name.startswith("worker."):
        return "agent"
    return "span"
