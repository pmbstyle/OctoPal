from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_COMPACTION_META_KEY = "__octopal_compaction__"
_MAX_RENDER_CHARS = 32_000
_MAX_CONTAINER_ITEMS = 48
_MAX_DEPTH = 8
_MAX_STRING_CHARS = 16_000
_CONTENT_HEAVY_MAX_RENDER_CHARS = 48_000
_CONTENT_HEAVY_MAX_STRING_CHARS = 24_000
_CONTENT_HEAVY_TOOL_NAMES = {
    "browser_extract",
    "markdown_new_fetch",
    "web_fetch",
}


@dataclass(frozen=True)
class RenderedToolResult:
    text: str
    was_compacted: bool


@dataclass(frozen=True)
class ToolRenderBudget:
    max_chars: int
    max_container_items: int
    max_depth: int
    max_string_chars: int


_DEFAULT_BUDGET = ToolRenderBudget(
    max_chars=_MAX_RENDER_CHARS,
    max_container_items=_MAX_CONTAINER_ITEMS,
    max_depth=_MAX_DEPTH,
    max_string_chars=_MAX_STRING_CHARS,
)
_CONTENT_HEAVY_BUDGET = ToolRenderBudget(
    max_chars=_CONTENT_HEAVY_MAX_RENDER_CHARS,
    max_container_items=_MAX_CONTAINER_ITEMS,
    max_depth=_MAX_DEPTH,
    max_string_chars=_CONTENT_HEAVY_MAX_STRING_CHARS,
)


def render_tool_result_for_llm(
    result: Any,
    *,
    tool_name: str | None = None,
    max_chars: int | None = None,
) -> RenderedToolResult:
    budget = _budget_for_tool(tool_name, max_chars=max_chars)
    compacted, was_compacted = _compact_tool_value(result, depth=0, budget=budget)
    if isinstance(compacted, str):
        rendered = compacted.strip()
    else:
        rendered = json.dumps(compacted, ensure_ascii=False, default=str)

    final_text = rendered.strip()
    if not final_text:
        return RenderedToolResult(text="", was_compacted=was_compacted)

    if len(final_text) <= budget.max_chars:
        return RenderedToolResult(text=final_text, was_compacted=was_compacted)

    omitted = len(final_text) - budget.max_chars
    truncated = final_text[: max(0, budget.max_chars - 32)].rstrip()
    suffix = f"... [truncated {omitted} chars]"
    return RenderedToolResult(text=f"{truncated}{suffix}", was_compacted=True)


def _budget_for_tool(tool_name: str | None, *, max_chars: int | None) -> ToolRenderBudget:
    normalized_name = str(tool_name or "").strip().lower()
    base_budget = _CONTENT_HEAVY_BUDGET if normalized_name in _CONTENT_HEAVY_TOOL_NAMES else _DEFAULT_BUDGET
    if max_chars is None:
        return base_budget
    return ToolRenderBudget(
        max_chars=max_chars,
        max_container_items=base_budget.max_container_items,
        max_depth=base_budget.max_depth,
        max_string_chars=base_budget.max_string_chars,
    )


def _compact_tool_value(value: Any, *, depth: int, budget: ToolRenderBudget) -> tuple[Any, bool]:
    if depth >= budget.max_depth:
        return _depth_marker(value), True

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return "", False
        parsed = _parse_json_like_string(stripped)
        if parsed is not None:
            compacted, _changed = _compact_tool_value(parsed, depth=depth + 1, budget=budget)
            return compacted, True
        if len(stripped) <= budget.max_string_chars:
            return stripped, False
        return _truncate_string(stripped, max_chars=budget.max_string_chars), True

    if isinstance(value, dict):
        compacted_items: dict[str, Any] = {}
        changed = False
        items = list(value.items())
        for key, raw_item in items[: budget.max_container_items]:
            compacted_item, item_changed = _compact_tool_value(raw_item, depth=depth + 1, budget=budget)
            compacted_items[str(key)] = compacted_item
            changed = changed or item_changed
        omitted = len(items) - len(compacted_items)
        compacted: dict[str, Any] = {}
        if changed or omitted > 0:
            meta: dict[str, Any] = {"compacted": True}
            if omitted > 0:
                meta.update({"omitted_keys": omitted, "original_keys": len(items)})
            _attach_compaction_meta(compacted, meta)
        compacted.update(compacted_items)
        if omitted > 0:
            changed = True
        return compacted, changed

    if isinstance(value, list | tuple | set):
        sequence = list(value)
        compacted_items: list[Any] = []
        changed = False
        for item in sequence[: budget.max_container_items]:
            compacted_item, item_changed = _compact_tool_value(item, depth=depth + 1, budget=budget)
            compacted_items.append(compacted_item)
            changed = changed or item_changed
        omitted = len(sequence) - len(compacted_items)
        if omitted > 0:
            changed = True
            compacted_items.append(
                f"... [{omitted} more {type(value).__name__} items omitted]"
            )
        return compacted_items, changed

    return value, False


def _parse_json_like_string(value: str) -> Any | None:
    if not value or value[0] not in "{[":
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _truncate_string(value: str, *, max_chars: int) -> str:
    omitted = len(value) - max_chars
    preview = value[: max_chars - 32].rstrip()
    return f"{preview}... [truncated {omitted} chars]"


def _depth_marker(value: Any) -> dict[str, Any]:
    return {
        _COMPACTION_META_KEY: {
            "reason": "max_depth_reached",
            "value_type": type(value).__name__,
        }
    }


def _attach_compaction_meta(target: dict[str, Any], meta: dict[str, Any]) -> None:
    key = _COMPACTION_META_KEY
    while key in target:
        key = f"_{key}"
    target[key] = meta
