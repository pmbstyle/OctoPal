from __future__ import annotations

import asyncio
import time
from pathlib import Path

from octopal.runtime.tool_errors import ToolBridgeError
from octopal.runtime.workers.agent_worker import (
    _auto_tune_max_steps,
    _classify_tool_error,
    _detect_orchestration_stall,
    _detect_tool_loop,
    _execute_tool,
    _extract_error_text,
    _extract_mcp_identity,
    _extract_tool_progress_key,
    _hash_tool_call,
    _hash_tool_outcome,
    _parse_tool_arguments,
    _resolve_tool_loop_thresholds,
    _result_has_error,
    _tool_progress_streak,
    execute_agent_task,
)
from octopal.runtime.workers.contracts import WorkerSpec
from octopal.runtime.workers.runtime import (
    _call_mcp_with_name_fallback,
    _extract_mcp_tool_identity,
)
from octopal.tools.registry import ToolSpec
from octopal.worker_sdk.worker import Worker


def _dummy_worker() -> Worker:
    spec = WorkerSpec(
        id="w1",
        task="t",
        inputs={},
        system_prompt="s",
        available_tools=[],
        mcp_tools=[],
        model=None,
        granted_capabilities=[],
        timeout_seconds=60,
        max_thinking_steps=5,
        run_id="r1",
        lifecycle="ephemeral",
        correlation_id=None,
    )
    return Worker(spec=spec)


def test_parse_tool_arguments_is_defensive() -> None:
    assert _parse_tool_arguments({"a": 1}) == {"a": 1}
    assert _parse_tool_arguments('{"a": 1}') == {"a": 1}
    assert _parse_tool_arguments("[1,2]") == {"_arg": [1, 2]}
    assert _parse_tool_arguments("{bad}") == {"_raw": "{bad}"}
    assert _parse_tool_arguments(None) == {}


def test_extract_mcp_identity_prefers_explicit_metadata() -> None:
    data = {
        "name": "mcp_demo_tool",
        "server_id": "demo_server",
        "remote_tool_name": "query_docs",
    }
    assert _extract_mcp_identity(data) == ("demo_server", "query_docs")


def test_extract_mcp_tool_identity_uses_longest_server_prefix() -> None:
    server_id, remote_name = _extract_mcp_tool_identity(
        "mcp_demo_server_query_docs",
        ["demo", "demo-server"],
    )
    assert server_id == "demo-server"
    assert remote_name == "query_docs"


def test_call_mcp_with_name_fallback_retries_not_found_variant() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def call_tool(self, tool_name: str, arguments: dict) -> dict:
            self.calls.append(tool_name)
            if tool_name == "list_threads":
                raise RuntimeError("Tool list_threads not found")
            if tool_name == "list-threads":
                return {"ok": True}
            raise RuntimeError("unexpected")

    async def scenario() -> tuple[dict, list[str]]:
        session = FakeSession()
        result = await _call_mcp_with_name_fallback(session, "list_threads", {})
        return result, session.calls

    result, calls = asyncio.run(scenario())
    assert result["ok"] is True
    assert calls == ["list_threads", "list-threads"]


def test_execute_tool_sync_handler_does_not_block_event_loop() -> None:
    worker = _dummy_worker()

    def slow_sync_handler(args, ctx):
        time.sleep(0.2)
        return {"ok": True, "args": args}

    tool = ToolSpec(
        name="slow_sync",
        description="slow",
        parameters={"type": "object"},
        permission="filesystem_read",
        handler=slow_sync_handler,
        is_async=False,
    )

    async def scenario() -> tuple[float, dict, dict]:
        start = time.perf_counter()
        task = asyncio.create_task(
            _execute_tool(
                "slow_sync",
                {"x": 1},
                Path("."),
                worker,
                {"slow_sync": tool},
                timeout_seconds=2,
            )
        )
        await asyncio.sleep(0.05)
        mid = time.perf_counter() - start
        result, meta = await task
        return mid, result, meta

    mid_elapsed, result, meta = asyncio.run(scenario())
    assert mid_elapsed < 0.15
    assert result["ok"] is True
    assert meta["had_error"] is False


def test_execute_tool_timeout_returns_error() -> None:
    worker = _dummy_worker()

    async def slow_async_handler(args, ctx):
        await asyncio.sleep(1.2)
        return {"ok": True}

    tool = ToolSpec(
        name="slow_async",
        description="slow",
        parameters={"type": "object"},
        permission="filesystem_read",
        handler=slow_async_handler,
        is_async=True,
    )

    async def scenario():
        return await _execute_tool(
            "slow_async",
            {},
            Path("."),
            worker,
            {"slow_async": tool},
            timeout_seconds=0,
        )

    # timeout_seconds=0 means no timeout (backward compatible)
    result, _meta = asyncio.run(scenario())
    assert result["ok"] is True

    async def scenario_timeout():
        return await _execute_tool(
            "slow_async",
            {},
            Path("."),
            worker,
            {"slow_async": tool},
            timeout_seconds=1,
        )

    timeout_result, timeout_meta = asyncio.run(scenario_timeout())
    assert "error" in timeout_result
    assert "timed out" in timeout_result["error"].lower()
    assert timeout_meta["timed_out"] is True
    assert timeout_meta["retries"] >= 1


def test_tool_error_classification() -> None:
    assert _classify_tool_error("connection timeout while fetching") == "transient"
    assert _classify_tool_error("permission denied by policy") == "permanent"


def test_plain_tool_error_strings_are_treated_as_errors() -> None:
    result = "run_skill_script error: skill 'job-search' has no scripts directory."
    assert _result_has_error(result) is True
    assert "no scripts directory" in _extract_error_text(result)


def test_execute_tool_preserves_structured_bridge_error_metadata() -> None:
    worker = _dummy_worker()

    async def broken_handler(args, ctx):
        raise ToolBridgeError(
            "schema mismatch",
            bridge="mcp",
            classification="schema_mismatch",
            retryable=False,
            server_id="demo",
            tool_name="get_thread",
        )

    tool = ToolSpec(
        name="mcp_demo_get_thread",
        description="broken",
        parameters={"type": "object"},
        permission="network",
        handler=broken_handler,
        is_async=True,
    )

    async def scenario():
        return await _execute_tool(
            "mcp_demo_get_thread",
            {},
            Path("."),
            worker,
            {"mcp_demo_get_thread": tool},
            timeout_seconds=5,
        )

    result, meta = asyncio.run(scenario())
    assert result["error"] == "schema mismatch"
    assert meta["had_error"] is True
    assert meta["error_type"] == "permanent"
    assert meta["error_bridge"] == "mcp"
    assert meta["error_classification"] == "schema_mismatch"


def test_auto_tune_max_steps_increases_for_web_and_mcp() -> None:
    tuned = _auto_tune_max_steps(8, ["web_search", "mcp_demo_read"], "Research worker")
    assert tuned > 8


def test_tool_call_hash_is_stable_for_key_order() -> None:
    h1 = _hash_tool_call("process", {"action": "poll", "id": 1})
    h2 = _hash_tool_call("process", {"id": 1, "action": "poll"})
    assert h1 == h2


def test_tool_progress_streak_counts_same_progress_key() -> None:
    history = [
        {"tool_name": "get_worker_result", "args_hash": "a", "result_hash": "x", "progress_key": None},
        {
            "tool_name": "synthesize_worker_results",
            "args_hash": "b",
            "result_hash": "1",
            "progress_key": "sig-1",
        },
        {"tool_name": "get_worker_result", "args_hash": "c", "result_hash": "y", "progress_key": None},
        {
            "tool_name": "synthesize_worker_results",
            "args_hash": "b",
            "result_hash": "2",
            "progress_key": "sig-1",
        },
        {
            "tool_name": "synthesize_worker_results",
            "args_hash": "b",
            "result_hash": "3",
            "progress_key": "sig-1",
        },
    ]
    count = _tool_progress_streak(
        history,
        tool_name="synthesize_worker_results",
        progress_key="sig-1",
    )
    assert count == 3


def test_extract_tool_progress_key_reads_synthesize_signature() -> None:
    assert (
        _extract_tool_progress_key(
            "synthesize_worker_results",
            {"progress_signature": "sig-1"},
        )
        == "sig-1"
    )
    assert _extract_tool_progress_key("get_worker_result", {"progress_signature": "sig-1"}) is None


def test_detect_orchestration_stall_warns_and_breaks_on_repeated_no_progress() -> None:
    history = [
        {
            "tool_name": "synthesize_worker_results",
            "args_hash": "same",
            "result_hash": "r1",
            "progress_key": "sig-1",
        },
        {
            "tool_name": "get_worker_result",
            "args_hash": "worker-1",
            "result_hash": "running",
            "progress_key": None,
        },
        {
            "tool_name": "synthesize_worker_results",
            "args_hash": "same",
            "result_hash": "r2",
            "progress_key": "sig-1",
        },
    ]
    warning = _detect_orchestration_stall(
        history,
        tool_name="synthesize_worker_results",
        tool_result={"pending_count": 2},
        progress_key="sig-1",
    )
    assert warning is not None
    assert warning["level"] == "warning"

    history.append(
        {
            "tool_name": "synthesize_worker_results",
            "args_hash": "same",
            "result_hash": "r3",
            "progress_key": "sig-1",
        }
    )
    critical = _detect_orchestration_stall(
        history,
        tool_name="synthesize_worker_results",
        tool_result={"pending_count": 2},
        progress_key="sig-1",
    )
    assert critical is not None
    assert critical["level"] == "critical"


def test_detect_tool_loop_warning_and_critical_thresholds() -> None:
    history_warning = [
        {"tool_name": "process", "args_hash": "a", "result_hash": "x"} for _ in range(8)
    ]
    warning = _detect_tool_loop(history_warning, tool_name="process", args_hash="a")
    assert warning is not None
    assert warning["level"] == "warning"

    history_critical = [
        {"tool_name": "process", "args_hash": "a", "result_hash": "x"} for _ in range(12)
    ]
    critical = _detect_tool_loop(history_critical, tool_name="process", args_hash="a")
    assert critical is not None
    assert critical["level"] == "critical"


def test_detect_tool_loop_global_circuit_breaker() -> None:
    history = [{"tool_name": "any", "args_hash": str(i), "result_hash": str(i)} for i in range(30)]
    state = _detect_tool_loop(history, tool_name="any", args_hash="29")
    assert state is not None
    assert state["detector"] == "global_circuit_breaker"


def test_tool_outcome_hash_changes_on_error_state() -> None:
    ok_hash = _hash_tool_outcome({"status": "ok"}, {"had_error": False, "timed_out": False})
    err_hash = _hash_tool_outcome({"status": "ok"}, {"had_error": True, "timed_out": False})
    assert ok_hash != err_hash


def test_resolve_tool_loop_thresholds_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_WARNING_THRESHOLD", "5")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_CRITICAL_THRESHOLD", "9")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_GLOBAL_BREAKER_THRESHOLD", "20")
    thresholds = _resolve_tool_loop_thresholds()
    assert thresholds == {"warning": 5, "critical": 9, "global_breaker": 20}


def test_resolve_tool_loop_thresholds_normalizes_invalid_order(monkeypatch) -> None:
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_WARNING_THRESHOLD", "10")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_CRITICAL_THRESHOLD", "10")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_GLOBAL_BREAKER_THRESHOLD", "1")
    thresholds = _resolve_tool_loop_thresholds()
    assert thresholds["warning"] == 10
    assert thresholds["critical"] == 11
    assert thresholds["global_breaker"] == 12


def test_resolve_tool_loop_thresholds_ignores_bad_values(monkeypatch) -> None:
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_WARNING_THRESHOLD", "oops")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_CRITICAL_THRESHOLD", "0")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_GLOBAL_BREAKER_THRESHOLD", "-3")
    thresholds = _resolve_tool_loop_thresholds()
    assert thresholds["warning"] >= 1
    assert thresholds["critical"] > thresholds["warning"]
    assert thresholds["global_breaker"] > thresholds["critical"]


def test_execute_agent_task_counts_completed_cycles_not_raw_llm_calls(monkeypatch, tmp_path: Path) -> None:
    worker = _dummy_worker()

    async def _noop_log(level: str, message: str) -> None:
        return None

    monkeypatch.setattr(worker, "log", _noop_log)
    monkeypatch.setattr("octopal.runtime.workers.agent_worker.load_settings", lambda: object())
    monkeypatch.setattr("octopal.runtime.workers.agent_worker.LiteLLMProvider", lambda settings, model=None, config=None: object())

    tool = ToolSpec(
        name="echo",
        description="echo",
        parameters={"type": "object"},
        permission="filesystem_read",
        handler=lambda args, ctx: {"ok": True},
        is_async=False,
    )
    monkeypatch.setattr("octopal.runtime.workers.agent_worker.get_tools", lambda: [tool])

    responses = iter(
        [
            {"content": ""},
            {"content": ""},
            {
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "echo", "arguments": "{\"value\": 1}"},
                    }
                ]
            },
            {"content": '{"type":"result","summary":"done"}'},
        ]
    )

    async def _fake_call_llm(provider, messages, tools):
        return next(responses)

    async def _fake_execute_tool(tool_name, tool_input, workspace_root, worker_dir, worker_obj, tool_map, *, timeout_seconds=None):
        return {"ok": True}, {"retries": 0, "timed_out": False, "had_error": False, "error_type": "none"}

    monkeypatch.setattr("octopal.runtime.workers.agent_worker._call_llm", _fake_call_llm)
    monkeypatch.setattr("octopal.runtime.workers.agent_worker._execute_tool", _fake_execute_tool)

    result = asyncio.run(execute_agent_task(worker, tmp_path, tmp_path))

    assert result.summary == "done"
    assert result.thinking_steps == 2
    assert result.tools_used == ["echo"]


def test_execute_agent_task_stops_after_repeated_empty_turns(monkeypatch, tmp_path: Path) -> None:
    worker = _dummy_worker()

    async def _noop_log(level: str, message: str) -> None:
        return None

    monkeypatch.setattr(worker, "log", _noop_log)
    monkeypatch.setattr("octopal.runtime.workers.agent_worker.load_settings", lambda: object())
    monkeypatch.setattr("octopal.runtime.workers.agent_worker.LiteLLMProvider", lambda settings, model=None, config=None: object())
    monkeypatch.setattr("octopal.runtime.workers.agent_worker.get_tools", lambda: [])

    async def _fake_call_llm(provider, messages, tools):
        return {"content": ""}

    monkeypatch.setattr("octopal.runtime.workers.agent_worker._call_llm", _fake_call_llm)

    result = asyncio.run(execute_agent_task(worker, tmp_path, tmp_path))

    assert result.summary == "Task stopped after 3 empty turns without progress"
    assert result.thinking_steps == 0
    assert isinstance(result.output, dict)
    assert result.output["reason"] == "empty_turn_limit"
    assert result.output["_telemetry"]["empty_turns"] == 3
