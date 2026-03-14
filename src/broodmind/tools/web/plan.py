from __future__ import annotations

import json
import time
from typing import Any

from broodmind.tools.browser.actions import browser_close, browser_open, browser_snapshot
from broodmind.tools.web.fetch import markdown_new_fetch, web_fetch


async def fetch_plan_tool(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Orchestrate URL fetching across markdown/web/browser strategies with traceable fallbacks."""
    url = str(args.get("url", "")).strip()
    if not url:
        return _to_json(
            {
                "ok": False,
                "degraded": True,
                "fallback_used": False,
                "error": "url is required",
                "plan": [],
            }
        )

    goal = str(args.get("goal", "quick_summary")).strip().lower()
    prefer_markdown = bool(args.get("prefer_markdown", True))
    allow_browser = bool(args.get("allow_browser", True))
    close_browser = bool(args.get("close_browser", True))
    max_chars = _bounded_int(args.get("max_chars"), default=20000, low=200, high=200000)
    min_content_chars = _bounded_int(args.get("min_content_chars"), default=700, low=100, high=10000)
    timeout_seconds = float(_bounded_int(args.get("timeout_seconds"), default=120, low=5, high=300))

    attempts: list[dict[str, Any]] = []
    budget_started = time.perf_counter()

    def remaining_budget() -> float:
        elapsed = time.perf_counter() - budget_started
        return max(1.0, timeout_seconds - elapsed)

    # Step 1: markdown_new_fetch (preferred)
    if prefer_markdown and remaining_budget() > 1.0:
        mk_args = {
            "url": url,
            "method": "auto",
            "max_chars": max_chars,
            "timeout_seconds": min(120, int(remaining_budget())),
            "fallback_to_web_fetch": False,
        }
        mk_result, mk_attempt = _run_sync_fetch("markdown_new_fetch", markdown_new_fetch, mk_args)
        attempts.append(mk_attempt)
        if mk_result.get("ok") and _has_enough_content(mk_result, min_content_chars):
            return _to_json(
                _build_success_payload(
                    url=url,
                    goal=goal,
                    source="markdown_new_fetch",
                    attempts=attempts,
                    result=mk_result,
                    degraded=False,
                    fallback_used=False,
                )
            )

    # Step 2: web_fetch fallback
    if remaining_budget() > 1.0:
        wf_args = {"url": url, "method": "GET", "max_chars": max_chars}
        wf_result, wf_attempt = _run_sync_fetch("web_fetch", web_fetch, wf_args)
        attempts.append(wf_attempt)
        if wf_result.get("ok") and _has_enough_content(wf_result, min_content_chars):
            return _to_json(
                _build_success_payload(
                    url=url,
                    goal=goal,
                    source="web_fetch",
                    attempts=attempts,
                    result=wf_result,
                    degraded=bool(prefer_markdown),
                    fallback_used=bool(prefer_markdown),
                )
            )

    # Step 3: browser snapshot fallback for JS-heavy pages
    if allow_browser and remaining_budget() > 1.0:
        browser_attempt = {"tool": "browser_snapshot_plan", "status": "error", "duration_ms": 0, "reason": ""}
        browser_start = time.perf_counter()
        try:
            open_resp = await browser_open({"url": url}, ctx)
            if str(open_resp).lower().startswith("error"):
                browser_attempt["reason"] = str(open_resp)
            else:
                snap = await browser_snapshot({}, ctx)
                if str(snap).lower().startswith("error"):
                    browser_attempt["reason"] = str(snap)
                else:
                    snippet = str(snap)[:max_chars]
                    browser_attempt["status"] = "ok"
                    browser_attempt["reason"] = "browser snapshot captured"
                    return _to_json(
                        {
                            "ok": True,
                            "degraded": True,
                            "fallback_used": True,
                            "rate_limited": False,
                            "source": "browser_snapshot",
                            "url": url,
                            "goal": goal,
                            "snippet": snippet,
                            "plan": attempts + [browser_attempt],
                            "next_best_action": "use browser_click/browser_type for deeper extraction if needed",
                        }
                    )
        except Exception as exc:
            browser_attempt["reason"] = f"browser exception: {exc}"
        finally:
            browser_attempt["duration_ms"] = int((time.perf_counter() - browser_start) * 1000)
            attempts.append(browser_attempt)
            if close_browser:
                try:
                    await browser_close({}, ctx)
                except Exception:
                    pass

    return _to_json(
        {
            "ok": False,
            "degraded": True,
            "fallback_used": len(attempts) > 1,
            "rate_limited": any("rate" in str(a.get("reason", "")).lower() for a in attempts),
            "source": "fetch_plan_tool",
            "url": url,
            "goal": goal,
            "error": "No fetch strategy produced sufficient content within budget",
            "plan": attempts,
            "next_best_action": "retry with allow_browser=true or lower min_content_chars",
        }
    )


def _run_sync_fetch(
    tool_name: str, handler: Any, call_args: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    try:
        raw = handler(call_args)
        parsed = _parse_fetch_output(raw)
        parsed.setdefault("ok", False)
        status = "ok" if parsed.get("ok") else "error"
        reason = str(parsed.get("error") or parsed.get("fallback_reason") or "")
        attempt = {
            "tool": tool_name,
            "status": status,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "reason": reason,
        }
        return parsed, attempt
    except Exception as exc:
        return (
            {"ok": False, "error": str(exc)},
            {
                "tool": tool_name,
                "status": "error",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "reason": str(exc),
            },
        )


def _build_success_payload(
    *,
    url: str,
    goal: str,
    source: str,
    attempts: list[dict[str, Any]],
    result: dict[str, Any],
    degraded: bool,
    fallback_used: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "degraded": degraded or bool(result.get("degraded", False)),
        "fallback_used": fallback_used or bool(result.get("fallback_used", False)),
        "rate_limited": bool(result.get("rate_limited", False)),
        "source": source,
        "url": url,
        "goal": goal,
        "snippet": str(result.get("snippet", "")),
        "status_code": result.get("status_code"),
        "content_type": result.get("content_type"),
        "plan": attempts,
    }


def _parse_fetch_output(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    lowered = text.lower()
    return {
        "ok": False,
        "error": text,
        "rate_limited": "429" in lowered or "rate limit" in lowered,
    }


def _has_enough_content(payload: dict[str, Any], min_chars: int) -> bool:
    snippet = str(payload.get("snippet", "") or "")
    return len(snippet.strip()) >= min_chars


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(low, min(high, parsed))


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
