from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_heartbeat_ok(text: str) -> bool:
    """Check if the text contains HEARTBEAT_OK (case-insensitive) and is exactly one line."""
    value = (text or "").strip()
    if not value:
        return False
    # Must contain HEARTBEAT_OK and have no internal newlines
    return "HEARTBEAT_OK" in value.upper() and "\n" not in value
