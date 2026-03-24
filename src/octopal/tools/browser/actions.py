from __future__ import annotations

from typing import Any

from playwright.async_api import Locator, Page

from octopal.browser.manager import get_browser_manager
from octopal.browser.snapshot import capture_aria_snapshot

# State to store refs per chat_id so they persist across tool calls in the same turn
_SESSION_REFS: dict[int, dict[str, Any]] = {}

def _get_chat_id(ctx: dict[str, Any]) -> int:
    return int(ctx.get("chat_id") or 0)

async def _get_locator(page: Page, ref: str, chat_id: int) -> Locator:
    """Resolve a [ref=eN] to a Playwright Locator."""
    refs = _SESSION_REFS.get(chat_id, {})
    if ref not in refs:
        raise ValueError(f"Unknown reference '{ref}'. Run browser_snapshot first.")

    info = refs[ref]
    role = info["role"]
    name = info.get("name")
    nth = info.get("nth", 0)

    locator = page.get_by_role(role, name=name, exact=True) if name else page.get_by_role(role)

    return locator.nth(nth)

async def browser_open(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Open a URL in the browser."""
    url = args.get("url")
    if not url:
        return "Error: url is required"

    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return f"Successfully opened {url}"
    except Exception as e:
        return f"Error opening {url}: {e}"

async def browser_snapshot(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Get an accessibility-based snapshot of the current page with stable refs."""
    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)

    try:
        result = await capture_aria_snapshot(page)
        _SESSION_REFS[chat_id] = result["refs"]
        return result["snapshot"]
    except Exception as e:
        return f"Error taking snapshot: {e}"

async def browser_click(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Click an element identified by a ref (e.g., 'e1')."""
    ref = args.get("ref")
    if not ref:
        return "Error: ref is required"

    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)

    try:
        locator = await _get_locator(page, ref, chat_id)
        await locator.click(timeout=5000)
        return f"Clicked {ref}"
    except Exception as e:
        return f"Error clicking {ref}: {e}"

async def browser_type(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Type text into an element identified by a ref."""
    ref = args.get("ref")
    text = args.get("text")
    press_enter = args.get("press_enter", False)

    if not ref or text is None:
        return "Error: ref and text are required"

    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)

    try:
        locator = await _get_locator(page, ref, chat_id)
        await locator.fill(text, timeout=5000)
        if press_enter:
            await locator.press("Enter")
        return f"Typed into {ref}"
    except Exception as e:
        return f"Error typing into {ref}: {e}"

async def browser_close(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Close the browser session for this chat."""
    chat_id = _get_chat_id(ctx)
    await get_browser_manager().close_chat_session(chat_id)
    _SESSION_REFS.pop(chat_id, None)
    return "Browser session closed"


async def browser_wait_for(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Wait for either a known ref or page text to appear."""
    ref = str(args.get("ref") or "").strip()
    text = str(args.get("text") or "").strip()
    state = str(args.get("state") or "visible").strip() or "visible"
    timeout_ms = int(args.get("timeout_ms") or 10000)

    if not ref and not text:
        return "Error: ref or text is required"

    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)

    try:
        if ref:
            locator = await _get_locator(page, ref, chat_id)
            await locator.wait_for(state=state, timeout=timeout_ms)
            return f"Element {ref} is now {state}"

        locator = page.get_by_text(text, exact=False).first
        await locator.wait_for(state=state, timeout=timeout_ms)
        return f"Text appeared: {text}"
    except Exception as e:
        target = ref or text
        return f"Error waiting for {target}: {e}"


async def browser_extract(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Extract visible text from a page or a specific ref."""
    ref = str(args.get("ref") or "").strip()
    max_chars = max(100, min(int(args.get("max_chars") or 4000), 20000))
    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)

    try:
        if ref:
            locator = await _get_locator(page, ref, chat_id)
            text = (await locator.inner_text(timeout=5000)).strip()
            return {
                "ok": True,
                "source": "ref",
                "ref": ref,
                "text": _truncate_text(text, max_chars=max_chars),
            }

        title = await page.title()
        body = await page.locator("body").inner_text(timeout=5000)
        return {
            "ok": True,
            "source": "page",
            "url": getattr(page, "url", ""),
            "title": title,
            "text": _truncate_text(body.strip(), max_chars=max_chars),
        }
    except Exception as e:
        return {
            "ok": False,
            "source": "ref" if ref else "page",
            "ref": ref or None,
            "error": str(e),
        }


async def browser_workflow(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Run a compact browser workflow made of existing browser actions."""
    raw_steps = args.get("steps")
    stop_on_error = bool(args.get("stop_on_error", True))
    if not isinstance(raw_steps, list) or not raw_steps:
        return {"ok": False, "error": "steps is required and must be a non-empty array"}

    results: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            results.append(
                {
                    "index": index,
                    "ok": False,
                    "error": "Each workflow step must be an object.",
                }
            )
            if stop_on_error:
                break
            continue

        action = str(raw_step.get("action") or "").strip().lower()
        step_args = {key: value for key, value in raw_step.items() if key != "action"}
        handler = _WORKFLOW_ACTIONS.get(action)
        if handler is None:
            results.append(
                {
                    "index": index,
                    "action": action,
                    "ok": False,
                    "error": f"Unsupported browser workflow action: {action}",
                }
            )
            if stop_on_error:
                break
            continue

        outcome = await handler(step_args, ctx)
        normalized = _normalize_workflow_outcome(index=index, action=action, outcome=outcome)
        results.append(normalized)
        if stop_on_error and not normalized["ok"]:
            break

    return {
        "ok": all(step["ok"] for step in results) if results else False,
        "step_count": len(results),
        "stop_on_error": stop_on_error,
        "steps": results,
    }


def _truncate_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[: max_chars - 32].rstrip() + f"... [truncated {omitted} chars]"


def _normalize_workflow_outcome(*, index: int, action: str, outcome: Any) -> dict[str, Any]:
    if isinstance(outcome, dict):
        payload = dict(outcome)
        payload.setdefault("ok", bool(payload.get("ok", True)))
        payload["index"] = index
        payload["action"] = action
        return payload

    text = str(outcome or "")
    ok = not text.lower().startswith("error")
    return {
        "index": index,
        "action": action,
        "ok": ok,
        "message": text,
    }


_WORKFLOW_ACTIONS = {
    "open": browser_open,
    "snapshot": browser_snapshot,
    "click": browser_click,
    "type": browser_type,
    "wait_for": browser_wait_for,
    "extract": browser_extract,
    "close": browser_close,
}
