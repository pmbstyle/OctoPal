from __future__ import annotations

DEFAULT_CAPABILITY_WHITELIST: dict[str, list[str]] = {
    "filesystem": ["/workspace/**"],
    "network": ["*"],
    "exec": ["python", "node"],
    "email": ["*"],
    "payment": [],
}
