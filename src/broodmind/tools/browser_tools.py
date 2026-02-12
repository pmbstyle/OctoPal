from __future__ import annotations

import json
from typing import Any, Dict, Optional
from playwright.async_api import Page, Locator
import structlog

from broodmind.browser.manager import get_browser_manager
from broodmind.browser.snapshot import capture_aria_snapshot

logger = structlog.get_logger(__name__)

# State to store refs per chat_id so they persist across tool calls in the same turn
_SESSION_REFS: Dict[int, Dict[str, Any]] = {}

def _get_chat_id(ctx: Dict[str, Any]) -> int:
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
    
    if name:
        locator = page.get_by_role(role, name=name, exact=True)
    else:
        locator = page.get_by_role(role)
        
    return locator.nth(nth)

async def browser_open(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
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

async def browser_snapshot(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Get an accessibility-based snapshot of the current page with stable refs."""
    chat_id = _get_chat_id(ctx)
    page = await get_browser_manager().get_page(chat_id)
    
    try:
        result = await capture_aria_snapshot(page)
        _SESSION_REFS[chat_id] = result["refs"]
        return result["snapshot"]
    except Exception as e:
        return f"Error taking snapshot: {e}"

async def browser_click(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
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

async def browser_type(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
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

async def browser_close(args: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Close the browser session for this chat."""
    chat_id = _get_chat_id(ctx)
    await get_browser_manager().close_chat_session(chat_id)
    _SESSION_REFS.pop(chat_id, None)
    return "Browser session closed"
