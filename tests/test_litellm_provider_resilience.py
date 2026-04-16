from __future__ import annotations

from octopal.infrastructure.providers.litellm_provider import _is_rate_limit_error


def test_is_rate_limit_error_detects_529_overload() -> None:
    exc = RuntimeError(
        'MinimaxException - {"type":"error","error":{"type":"overloaded_error","message":"The server cluster is currently under high load.","http_code":"529"}}'
    )
    assert _is_rate_limit_error(exc) is True
