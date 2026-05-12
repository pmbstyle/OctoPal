from __future__ import annotations

import re
from typing import Any

_WORKER_TIMEOUT_MIN_SECONDS = 30
_WORKER_TIMEOUT_MAX_SECONDS = 1800
_TIMEOUT_STEP_PATTERN = re.compile(r"(?im)^\s*(?:step\s+\d+[:.)-]?|\d+[.)]|[-*])\s+")
_NETWORK_TOOL_MARKERS = (
    "mcp_",
    "web_",
    "browser",
    "fetch",
    "search",
    "crawl",
    "http",
    "api",
)
_CONTEXT_HEAVY_TASK_MARKERS = (
    "full",
    "entire",
    "whole",
    "conversation",
    "thread",
    "history",
    "transcript",
    "timeline",
    "dm",
    "inbox",
    "mailbox",
    "email",
    "messages",
    "message history",
    "read through",
    "catch up",
    "review",
    "digest",
    "summarize",
)
_SYNTHESIS_HEAVY_TASK_MARKERS = (
    "reply",
    "respond",
    "draft",
    "write back",
    "thoughtful",
    "careful",
    "analyze",
    "compare",
    "recommend",
    "decide",
)


def _clamp_worker_timeout(timeout_seconds: float) -> int:
    return max(
        _WORKER_TIMEOUT_MIN_SECONDS,
        min(_WORKER_TIMEOUT_MAX_SECONDS, int(round(timeout_seconds))),
    )


def _resolve_worker_timeout_seconds(
    *,
    explicit_timeout_seconds: int | None,
    template: Any | None,
    task: str,
    tools: list[str] | None,
    scheduled_task_id: str | None,
) -> tuple[int, dict[str, Any]]:
    """Resolve worker timeout from explicit override or task/template heuristics."""
    if explicit_timeout_seconds is not None:
        explicit = max(1, int(explicit_timeout_seconds))
        return explicit, {"source": "explicit", "reasons": ["explicit_override"]}

    template_default = int(getattr(template, "default_timeout_seconds", 300) or 300)
    timeout = float(max(_WORKER_TIMEOUT_MIN_SECONDS, template_default))
    reasons: list[str] = [f"template_default={template_default}"]

    effective_tools = [
        str(tool_name).strip().lower()
        for tool_name in (tools or getattr(template, "available_tools", []) or [])
        if str(tool_name).strip()
    ]
    permissions = {
        str(permission).strip().lower()
        for permission in (getattr(template, "required_permissions", []) or [])
        if str(permission).strip()
    }
    lowered_task = (task or "").lower()
    word_count = len(re.findall(r"\w+", lowered_task))
    step_count = len(_TIMEOUT_STEP_PATTERN.findall(task or ""))
    network_bound = "network" in permissions or any(
        marker in tool_name for tool_name in effective_tools for marker in _NETWORK_TOOL_MARKERS
    )
    context_hits = sum(1 for marker in _CONTEXT_HEAVY_TASK_MARKERS if marker in lowered_task)
    synthesis_hits = sum(1 for marker in _SYNTHESIS_HEAVY_TASK_MARKERS if marker in lowered_task)

    if scheduled_task_id:
        timeout = max(timeout, 180.0)
        reasons.append("scheduled_task")
    if network_bound:
        timeout *= 1.25
        reasons.append("network_bound")
    if step_count >= 2:
        timeout *= 1.0 + min(0.30, (step_count - 1) * 0.10)
        reasons.append(f"step_count={step_count}")
    if word_count >= 80:
        timeout *= 1.15
        reasons.append(f"task_words={word_count}")
    if context_hits >= 2:
        timeout *= 1.30
        reasons.append(f"context_heavy={context_hits}")
    elif context_hits == 1:
        timeout *= 1.15
        reasons.append("context_heavy=1")
    if synthesis_hits >= 2:
        timeout *= 1.20
        reasons.append(f"synthesis_heavy={synthesis_hits}")
    elif synthesis_hits == 1:
        timeout *= 1.10
        reasons.append("synthesis_heavy=1")
    if context_hits and synthesis_hits:
        timeout = max(timeout, template_default * 2.0)
        reasons.append("retrieve_then_synthesize")

    return _clamp_worker_timeout(timeout), {"source": "policy", "reasons": reasons}
