from __future__ import annotations

import pytest

from broodmind.runtime.queen.router import _handle_queen_tool_call, _record_queen_tool_call
from broodmind.tools.registry import ToolSpec


def _tool(name: str, *, handler, is_async: bool = False) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"{name} tool",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        permission="network",
        handler=handler,
        is_async=is_async,
    )


@pytest.mark.asyncio
async def test_handle_queen_tool_call_reports_unknown_tool() -> None:
    result, meta = await _handle_queen_tool_call(
        {"function": {"name": "missing_tool", "arguments": "{}"}},
        [],
        {},
    )

    assert result == {"error": "Unknown tool: missing_tool"}
    assert meta["had_error"] is True


@pytest.mark.asyncio
async def test_handle_queen_tool_call_captures_tool_exceptions() -> None:
    def _boom(_args, _ctx):
        raise RuntimeError("kaboom")

    result, meta = await _handle_queen_tool_call(
        {"function": {"name": "web_search", "arguments": "{}"}},
        [_tool("web_search", handler=_boom)],
        {},
    )

    assert "kaboom" in result["error"]
    assert meta["had_error"] is True


def test_record_queen_tool_call_returns_warning_for_repeated_no_progress() -> None:
    history: list[dict[str, str]] = []
    call = {"function": {"name": "web_search", "arguments": '{"query":"same"}'}}
    thresholds = {"warning": 3, "critical": 5, "global_breaker": 10}

    state = None
    for _ in range(3):
        state = _record_queen_tool_call(
            history,
            call=call,
            tool_result={"items": []},
            tool_meta={"had_error": False, "timed_out": False},
            thresholds=thresholds,
        )

    assert state is not None
    assert state["level"] == "warning"


def test_record_queen_tool_call_returns_critical_for_global_breaker() -> None:
    history: list[dict[str, str]] = []
    thresholds = {"warning": 3, "critical": 5, "global_breaker": 4}

    state = None
    for idx in range(4):
        state = _record_queen_tool_call(
            history,
            call={"function": {"name": f"tool_{idx}", "arguments": "{}"}},
            tool_result={"ok": idx},
            tool_meta={"had_error": False, "timed_out": False},
            thresholds=thresholds,
        )

    assert state is not None
    assert state["level"] == "critical"
    assert state["detector"] == "global_circuit_breaker"
