from __future__ import annotations

from octopal.infrastructure.config.settings import Settings
from octopal.infrastructure.observability import build_trace_sink
from octopal.infrastructure.observability.noop import NoopTraceSink


def test_build_trace_sink_returns_noop_when_disabled() -> None:
    settings = Settings(
        OCTOPAL_OBSERVABILITY_ENABLED=False,
    )

    sink = build_trace_sink(settings)

    assert isinstance(sink, NoopTraceSink)


def test_build_trace_sink_falls_back_to_noop_when_langfuse_init_fails(monkeypatch) -> None:
    def _boom(**kwargs):
        raise ImportError("langfuse missing")

    monkeypatch.setattr("octopal.infrastructure.observability.LangfuseTraceSink", _boom)

    settings = Settings(
        OCTOPAL_OBSERVABILITY_ENABLED=True,
        OCTOPAL_OBSERVABILITY_BACKEND="langfuse",
        LANGFUSE_PUBLIC_KEY="pk-test",
        LANGFUSE_SECRET_KEY="sk-test",
    )

    sink = build_trace_sink(settings)

    assert isinstance(sink, NoopTraceSink)
