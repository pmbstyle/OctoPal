from __future__ import annotations

from octopal.runtime.tool_loop import (
    _detect_tool_loop,
    _hash_tool_call,
    _hash_tool_outcome,
    _resolve_tool_loop_thresholds,
    _tool_no_progress_streak,
)


def test_hash_tool_call_is_stable_for_same_payload() -> None:
    one = _hash_tool_call("web_search", {"query": "octopal"})
    two = _hash_tool_call("web_search", {"query": "octopal"})
    assert one == two


def test_tool_no_progress_streak_counts_matching_tail() -> None:
    history = [
        {"tool_name": "web_search", "args_hash": "a", "result_hash": "x"},
        {"tool_name": "web_search", "args_hash": "a", "result_hash": "x"},
        {"tool_name": "web_search", "args_hash": "a", "result_hash": "x"},
    ]

    count, latest = _tool_no_progress_streak(history, tool_name="web_search", args_hash="a")
    assert count == 3
    assert latest == "x"


def test_detect_tool_loop_returns_critical_after_threshold() -> None:
    history = [{"tool_name": "web_search", "args_hash": "a", "result_hash": "x"} for _ in range(12)]
    state = _detect_tool_loop(history, tool_name="web_search", args_hash="a")

    assert state is not None
    assert state["level"] == "critical"


def test_hash_tool_outcome_changes_when_error_flag_changes() -> None:
    ok_hash = _hash_tool_outcome({"items": []}, {"had_error": False, "timed_out": False})
    error_hash = _hash_tool_outcome({"items": []}, {"had_error": True, "timed_out": False})

    assert ok_hash != error_hash


def test_resolve_tool_loop_thresholds_normalizes_invalid_order(monkeypatch) -> None:
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_WARNING_THRESHOLD", "10")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_CRITICAL_THRESHOLD", "10")
    monkeypatch.setenv("OCTOPAL_TOOL_LOOP_GLOBAL_BREAKER_THRESHOLD", "1")

    thresholds = _resolve_tool_loop_thresholds()

    assert thresholds["warning"] == 10
    assert thresholds["critical"] == 11
    assert thresholds["global_breaker"] == 12
