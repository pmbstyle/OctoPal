from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx


DEFAULT_MAX_CHARS = 20000


def web_fetch(args: dict[str, Any]) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        return "web_fetch error: url is required."
    if not _is_safe_url(url):
        return "web_fetch error: url not allowed."
    max_chars_raw = args.get("max_chars", DEFAULT_MAX_CHARS)
    try:
        max_chars = int(max_chars_raw)
    except Exception:
        max_chars = DEFAULT_MAX_CHARS
    max_chars = max(200, min(200000, max_chars))
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; BroodMind/1.0)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            resp = client.get(url)
        content = resp.text
        snippet = content[:max_chars]
        payload = {
            "url": url,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type"),
            "snippet": snippet,
        }
        return _to_json(payload)
    except Exception as exc:
        return f"web_fetch error: {exc}"


def _is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    return True


def _to_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
