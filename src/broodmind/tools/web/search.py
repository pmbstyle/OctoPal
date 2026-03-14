from __future__ import annotations

import os
from typing import Any

import httpx

BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_COUNT = 5
MAX_COUNT = 10


def web_search(args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "web_search error: query is required."
    count_raw = args.get("count", DEFAULT_COUNT)
    try:
        count = int(count_raw)
    except Exception:
        count = DEFAULT_COUNT
    count = max(1, min(MAX_COUNT, count))
    country = str(args.get("country", "")).strip() or None
    search_lang = str(args.get("search_lang", "")).strip() or None
    ui_lang = str(args.get("ui_lang", "")).strip() or None
    freshness = str(args.get("freshness", "")).strip() or None

    api_key = (os.getenv("BRAVE_API_KEY") or "").strip()
    if not api_key:
        return "web_search error: missing BRAVE_API_KEY."

    params = {"q": query, "count": str(count)}
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang
    if ui_lang:
        params["ui_lang"] = ui_lang
    if freshness:
        params["freshness"] = freshness

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                BRAVE_SEARCH_ENDPOINT,
                params=params,
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"web_search error: {exc}"

    results = []
    for entry in (data.get("web", {}) or {}).get("results", []) or []:
        results.append(
            {
                "title": entry.get("title") or "",
                "url": entry.get("url") or "",
                "description": entry.get("description") or "",
                "published": entry.get("age"),
            }
        )
    return _to_json({"query": query, "count": len(results), "results": results})


def _to_json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
