from __future__ import annotations

from typing import Any

from octopal.tools.web.providers.registry import resolve_search_provider, run_search


def web_search(args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return _to_json(
            {
                "ok": False,
                "degraded": False,
                "fallback_used": False,
                "rate_limited": False,
                "source": "web_search",
                "provider": resolve_search_provider(args),
                "error": "query is required",
            }
        )
    return _to_json(run_search(args))


def _to_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
