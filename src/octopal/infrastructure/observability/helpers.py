from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s,;]+)"),
    re.compile(r"(?i)\b(bearer\s+)([^\s,;]+)"),
    re.compile(r'(?i)\b(api[_ -]?key|token|secret|password)\b(\s*[:=]\s*)(["\']?)([^"\'\s,;]+)\3'),
    re.compile(r"\b(?:moltbook|openai|sk|rk)_[A-Za-z0-9_-]{12,}\b"),
)


def preview_text(value: str | None, limit: int = 240) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"...[truncated {len(text) - limit} chars]"


def mask_secrets(value: str | None) -> str:
    masked = str(value or "")
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub(_mask_match, masked)
    return masked


def hash_payload(value: Any) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        serialized = repr(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def summarize_exception(exc: Exception) -> dict[str, str]:
    return {
        "error_type": exc.__class__.__name__,
        "error_message_short": preview_text(mask_secrets(str(exc)), limit=240),
    }


def safe_preview(value: Any, limit: int = 240) -> str:
    try:
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        rendered = repr(value)
    return preview_text(mask_secrets(rendered), limit=limit)


def _mask_match(match: re.Match[str]) -> str:
    groups = match.groups()
    if not groups:
        return "[redacted]"
    if len(groups) == 2:
        return f"{groups[0]}[redacted]"
    if len(groups) >= 4:
        prefix = "".join(str(group or "") for group in groups[:-1])
        return f"{prefix}[redacted]"
    return "[redacted]"
