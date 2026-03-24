from __future__ import annotations

from octopal.runtime.octo.router import _extract_json_object, _normalize_plan_payload


def test_extract_json_object_handles_plain_json() -> None:
    payload = _extract_json_object('{"mode":"execute","steps":["a","b"]}')
    assert payload is not None
    assert payload["mode"] == "execute"


def test_extract_json_object_handles_fenced_json() -> None:
    payload = _extract_json_object('```json\n{"mode":"reply","response":"ok"}\n```')
    assert payload is not None
    assert payload["mode"] == "reply"


def test_normalize_plan_payload_reply_mode_requires_response() -> None:
    assert _normalize_plan_payload({"mode": "reply"}, has_tools=True) is None
    plan = _normalize_plan_payload({"mode": "reply", "response": "done"}, has_tools=True)
    assert plan == {"mode": "reply", "response": "done", "steps": []}


def test_normalize_plan_payload_execute_mode_requires_steps() -> None:
    assert _normalize_plan_payload({"mode": "execute", "steps": []}, has_tools=True) is None
    plan = _normalize_plan_payload({"mode": "execute", "steps": ["one", "two"]}, has_tools=True)
    assert plan is not None
    assert plan["mode"] == "execute"
    assert plan["steps"] == ["one", "two"]


def test_normalize_plan_payload_degrades_execute_to_reply_without_tools() -> None:
    plan = _normalize_plan_payload(
        {"mode": "execute", "steps": ["use tool"], "response": "direct answer"},
        has_tools=False,
    )
    assert plan == {"mode": "reply", "response": "direct answer", "steps": []}
