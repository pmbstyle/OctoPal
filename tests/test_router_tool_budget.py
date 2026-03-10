from __future__ import annotations

import asyncio

from broodmind.queen.router import (
    _budget_tool_specs,
    _build_partial_callback,
    _sanitize_partial_for_user,
    _shrink_tool_specs_for_retry,
)
from broodmind.providers.base import Message
from broodmind.tools.tools import get_tools
from broodmind.tools.registry import ToolSpec


def test_budget_keeps_internal_worker_and_scheduler_tools() -> None:
    all_tools = get_tools(mcp_manager=None)
    budgeted = _budget_tool_specs(all_tools, max_count=8)
    names = {spec.name for spec in budgeted}

    must_keep = {
        "check_schedule",
        "start_worker",
        "get_worker_status",
        "get_worker_result",
        "list_workers",
        "list_active_workers",
        "schedule_task",
    }
    assert must_keep.issubset(names)


def test_shrink_retry_keeps_start_worker() -> None:
    all_tools = get_tools(mcp_manager=None)
    shrunk = _shrink_tool_specs_for_retry(all_tools)
    names = {spec.name for spec in shrunk}
    assert "start_worker" in names


def test_route_falls_back_when_tool_run_ends_with_empty_response(monkeypatch) -> None:
    class DummyProvider:
        def __init__(self) -> None:
            self.tool_calls = 0

        async def complete(self, messages, **kwargs):
            return "I checked it and I'm still working through the result."

        async def complete_stream(self, messages, *, on_partial, **kwargs):
            raise AssertionError("streaming should not be used in this test")

        async def complete_with_tools(self, messages, *, tools, tool_choice="auto", **kwargs):
            self.tool_calls += 1
            if self.tool_calls == 1:
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "dummy_tool", "arguments": "{}"},
                        }
                    ],
                }
            return {"content": "", "tool_calls": []}

    class DummyMemory:
        async def add_message(self, role, content, metadata=None):
            return None

    class DummyQueen:
        store = object()
        canon = object()
        internal_progress_send = None
        is_ws_active = False

        def __init__(self) -> None:
            self.thinking_states: list[bool] = []
            self.typing_states: list[tuple[int, bool]] = []

        async def set_typing(self, chat_id: int, active: bool) -> None:
            self.typing_states.append((chat_id, active))

        async def set_thinking(self, active: bool) -> None:
            self.thinking_states.append(active)

        def peek_context_wakeup(self, chat_id: int) -> str:
            return ""

    async def fake_build_queen_prompt(**kwargs):
        return [Message(role="user", content=str(kwargs["user_text"]))]

    async def fake_build_plan(provider, messages, has_tools):
        return {"mode": "execute", "steps": ["run dummy tool"], "response": ""}

    def dummy_tool(args, ctx):
        return {"ok": True}

    def fake_get_queen_tools(queen, chat_id):
        return (
            [
                ToolSpec(
                    name="dummy_tool",
                    description="dummy",
                    parameters={"type": "object", "properties": {}},
                    permission="exec",
                    handler=dummy_tool,
                )
            ],
            {"queen": queen, "chat_id": chat_id},
        )

    import broodmind.queen.router as router

    monkeypatch.setattr(router, "build_queen_prompt", fake_build_queen_prompt)
    monkeypatch.setattr(router, "_build_plan", fake_build_plan)
    monkeypatch.setattr(router, "_get_queen_tools", fake_get_queen_tools)

    async def scenario() -> None:
        provider = DummyProvider()
        queen = DummyQueen()
        response = await router.route_or_reply(
            queen,
            provider,
            DummyMemory(),
            "check this",
            123,
            "",
        )
        assert response == "I checked it and I'm still working through the result."
        assert provider.tool_calls == 2

    asyncio.run(scenario())


def test_sanitize_partial_for_user_drops_tool_lines() -> None:
    raw = (
        "Обновляю daily notes с telegram morning report:\n"
        'fs_read(file_path="memory/2026-03-10.md")\n'
        'fs_writeландшафтный_path="/">memory/2026-03-10.md" content="...append..."\n'
        "Проверяю, все ли сохранилось."
    )

    assert _sanitize_partial_for_user(raw) == (
        "Обновляю daily notes с telegram morning report:\n"
        "Проверяю, все ли сохранилось."
    )


def test_partial_callback_suppresses_raw_tool_command() -> None:
    calls: list[str] = []

    class DummyQueen:
        async def internal_progress_send(self, chat_id: int, state: str, text: str, meta: dict) -> None:
            calls.append(text)

    async def scenario() -> None:
        callback = _build_partial_callback(queen=DummyQueen(), chat_id=123, internal_followup=False)
        assert callback is not None
        await callback("check_schedule")
        await callback("Проверяю статус worker-а.")

    asyncio.run(scenario())
    assert calls == ["Проверяю статус worker-а."]


def test_route_tool_fallback_does_not_stream_partials_even_when_preview_sender_exists(monkeypatch) -> None:
    class DummyProvider:
        def __init__(self) -> None:
            self.tool_calls = 0

        async def complete(self, messages, **kwargs):
            return "Проверила результат и продолжаю работу."

        async def complete_stream(self, messages, *, on_partial, **kwargs):
            raise AssertionError("tool fallback should not use streaming partials")

        async def complete_with_tools(self, messages, *, tools, tool_choice="auto", **kwargs):
            self.tool_calls += 1
            if self.tool_calls == 1:
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "dummy_tool", "arguments": "{}"},
                        }
                    ],
                }
            return {"content": "", "tool_calls": []}

    class DummyMemory:
        async def add_message(self, role, content, metadata=None):
            return None

    class DummyQueen:
        store = object()
        canon = object()
        is_ws_active = False

        def __init__(self) -> None:
            self.progress: list[str] = []

        async def set_typing(self, chat_id: int, active: bool) -> None:
            return None

        async def set_thinking(self, active: bool) -> None:
            return None

        def peek_context_wakeup(self, chat_id: int) -> str:
            return ""

        async def internal_progress_send(self, chat_id: int, state: str, text: str, meta: dict) -> None:
            self.progress.append(text)

    async def fake_build_queen_prompt(**kwargs):
        return [Message(role="user", content=str(kwargs["user_text"]))]

    async def fake_build_plan(provider, messages, has_tools):
        return {"mode": "execute", "steps": ["run dummy tool"], "response": ""}

    def dummy_tool(args, ctx):
        return {"ok": True}

    def fake_get_queen_tools(queen, chat_id):
        return (
            [
                ToolSpec(
                    name="dummy_tool",
                    description="dummy",
                    parameters={"type": "object", "properties": {}},
                    permission="exec",
                    handler=dummy_tool,
                )
            ],
            {"queen": queen, "chat_id": chat_id},
        )

    import broodmind.queen.router as router

    monkeypatch.setattr(router, "build_queen_prompt", fake_build_queen_prompt)
    monkeypatch.setattr(router, "_build_plan", fake_build_plan)
    monkeypatch.setattr(router, "_get_queen_tools", fake_get_queen_tools)

    async def scenario() -> None:
        provider = DummyProvider()
        queen = DummyQueen()
        response = await router.route_or_reply(
            queen,
            provider,
            DummyMemory(),
            "check this",
            123,
            "",
        )
        assert response == "Проверила результат и продолжаю работу."
        assert provider.tool_calls == 2
        assert queen.progress == []

    asyncio.run(scenario())
