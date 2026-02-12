from __future__ import annotations

import asyncio
from typing import Dict, Optional, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
import structlog

logger = structlog.get_logger(__name__)

class BrowserManager:
    """Manages Playwright browser instances and contexts for multiple agents/chats."""
    
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: Dict[int, BrowserContext] = {}
        self._pages: Dict[int, Page] = {}
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
                logger.info("Playwright browser started")

    async def get_page(self, chat_id: int) -> Page:
        """Get or create an isolated page for a specific chat/agent."""
        await self._ensure_browser()
        
        async with self._lock:
            if chat_id not in self._contexts:
                # Create a new isolated context for this chat
                context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                self._contexts[chat_id] = context
                page = await context.new_page()
                self._pages[chat_id] = page
                logger.info("Created new browser context and page", chat_id=chat_id)
            
            return self._pages[chat_id]

    async def close_chat_session(self, chat_id: int):
        """Close the context and page for a specific chat."""
        async with self._lock:
            page = self._pages.pop(chat_id, None)
            context = self._contexts.pop(chat_id, None)
            
            if page:
                await page.close()
            if context:
                await context.close()
            
            logger.info("Closed browser session", chat_id=chat_id)

    async def shutdown(self):
        """Shutdown the entire browser manager."""
        async with self._lock:
            for page in self._pages.values():
                await page.close()
            for context in self._contexts.values():
                await context.close()
            
            self._pages.clear()
            self._contexts.clear()
            
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            
            self._browser = None
            self._playwright = None
            logger.info("Browser manager shut down")

# Global singleton
_manager = BrowserManager()

def get_browser_manager() -> BrowserManager:
    return _manager
