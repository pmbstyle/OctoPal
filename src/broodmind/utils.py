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


def is_control_response(text: str) -> bool:
    """Check if the text is a system control message like HEARTBEAT_OK or NO_USER_RESPONSE."""
    value = (text or "").strip()
    if not value:
        return True
        
    if is_heartbeat_ok(value):
        return True
        
    # Check for NO_USER_RESPONSE variations
    normalized = value.upper().replace("_", "").replace(" ", "")
    if normalized == "NOUSERRESPONSE":
        return True
        
    return False
