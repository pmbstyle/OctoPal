from __future__ import annotations

import structlog

from octopal.infrastructure.config.settings import Settings
from octopal.infrastructure.observability.base import (
    TraceContext,
    TraceSink,
    bind_trace_context,
    get_current_trace_context,
    now_ms,
    reset_trace_context,
)
from octopal.infrastructure.observability.langfuse_sink import LangfuseTraceSink
from octopal.infrastructure.observability.noop import NoopTraceSink

logger = structlog.get_logger(__name__)


def build_trace_sink(settings: Settings) -> TraceSink:
    if not settings.observability_enabled:
        return NoopTraceSink()

    backend = str(settings.observability_backend or "noop").strip().lower()
    if backend == "noop":
        return NoopTraceSink()

    if backend != "langfuse":
        logger.warning(
            "Unknown observability backend; using noop sink",
            backend=backend,
        )
        return NoopTraceSink()

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse observability is enabled but credentials are missing; using noop sink"
        )
        return NoopTraceSink()

    try:
        return LangfuseTraceSink(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            sample_rate=settings.observability_sample_rate,
            tracing_enabled=True,
        )
    except ImportError:
        logger.warning("Langfuse backend requested but package is not installed; using noop sink")
    except Exception:
        logger.warning("Failed to initialize Langfuse sink; using noop sink", exc_info=True)
    return NoopTraceSink()


__all__ = [
    "NoopTraceSink",
    "TraceContext",
    "TraceSink",
    "bind_trace_context",
    "build_trace_sink",
    "get_current_trace_context",
    "now_ms",
    "reset_trace_context",
]
