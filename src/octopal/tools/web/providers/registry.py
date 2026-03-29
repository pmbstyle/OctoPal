from __future__ import annotations

from typing import Any

from octopal.tools.web.providers import brave_provider, firecrawl_provider

SEARCH_PROVIDER_ORDER = ("brave", "firecrawl")


def resolve_search_provider(args: dict[str, Any]) -> str | None:
    requested = str(args.get("provider", "auto") or "auto").strip().lower()
    if requested in {"brave", "firecrawl"}:
        return requested
    if requested != "auto":
        return None

    for provider in SEARCH_PROVIDER_ORDER:
        if provider == "brave" and brave_provider.is_configured():
            return provider
        if provider == "firecrawl" and firecrawl_provider.is_configured():
            return provider
    return None


def run_search(args: dict[str, Any]) -> dict[str, Any]:
    provider = resolve_search_provider(args)
    if provider is None:
        return {
            "ok": False,
            "degraded": False,
            "fallback_used": False,
            "rate_limited": False,
            "source": "web_search",
            "provider": None,
            "error": "no configured search provider available",
        }

    if provider == "brave":
        return brave_provider.search(args)
    if provider == "firecrawl":
        return firecrawl_provider.search(args)

    return {
        "ok": False,
        "degraded": False,
        "fallback_used": False,
        "rate_limited": False,
        "source": "web_search",
        "provider": provider,
        "error": f"unsupported search provider: {provider}",
    }
