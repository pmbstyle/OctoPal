from __future__ import annotations

import asyncio
import types

from octopal.infrastructure.config.settings import Settings
from octopal.infrastructure.observability import build_trace_sink
from octopal.infrastructure.observability.langfuse_sink import LangfuseTraceSink
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


def test_langfuse_trace_sink_uses_current_python_sdk_api(monkeypatch) -> None:
    created_clients: list[FakeLangfuse] = []

    class FakeContextManager:
        def __init__(self, observation: FakeObservation) -> None:
            self.observation = observation
            self.exited = False

        def __enter__(self) -> FakeObservation:
            return self.observation

        def __exit__(self, exc_type, exc, tb) -> None:
            self.exited = True

    class FakeObservation:
        def __init__(self, name: str, as_type: str, metadata=None, input=None) -> None:
            self.name = name
            self.as_type = as_type
            self.metadata = metadata
            self.input = input
            self.children: list[FakeObservation] = []
            self.updates: list[dict[str, object]] = []

        def start_as_current_observation(self, **kwargs) -> FakeContextManager:
            child = FakeObservation(
                kwargs.get("name", ""),
                kwargs.get("as_type", "span"),
                metadata=kwargs.get("metadata"),
                input=kwargs.get("input"),
            )
            self.children.append(child)
            return FakeContextManager(child)

        def update(self, **kwargs) -> None:
            self.updates.append(kwargs)

    class FakeLangfuse:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.root_observations: list[FakeObservation] = []
            created_clients.append(self)

        def start_as_current_observation(self, **kwargs) -> FakeContextManager:
            observation = FakeObservation(
                kwargs.get("name", ""),
                kwargs.get("as_type", "span"),
                metadata=kwargs.get("metadata"),
                input=kwargs.get("input"),
            )
            self.root_observations.append(observation)
            return FakeContextManager(observation)

    fake_module = types.ModuleType("langfuse")
    fake_module.Langfuse = FakeLangfuse
    monkeypatch.setitem(__import__("sys").modules, "langfuse", fake_module)

    async def scenario() -> None:
        sink = LangfuseTraceSink(
            public_key="pk-test",
            secret_key="sk-test",
            host="https://example.com",
            sample_rate=1.0,
        )
        trace = await sink.start_trace(
            name="octo.turn",
            trace_id="turn-123",
            root_trace_id="turn-123",
            session_id="chat:1",
            chat_id=1,
            input={"text": "hello"},
            metadata={"stage": "root"},
        )
        child = await sink.start_span(
            trace,
            name="worker.run",
            metadata={"stage": "child"},
        )
        await sink.finish_span(child, output={"status": "ok"})
        await sink.finish_trace(trace, output={"status": "ok"})

    asyncio.run(scenario())

    client = created_clients[0]
    assert client.kwargs["public_key"] == "pk-test"
    assert client.root_observations[0].name == "octo.turn"
    assert client.root_observations[0].children[0].name == "worker.run"
    assert client.root_observations[0].children[0].as_type == "agent"
