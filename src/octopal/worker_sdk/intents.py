from __future__ import annotations

from octopal.runtime.intents.types import IntentRequest


def http_get(url: str, headers: dict[str, str] | None = None) -> IntentRequest:
    payload: dict[str, object] = {"url": url}
    if headers:
        payload["headers"] = headers
    return IntentRequest(type="http.get", payload=payload)
