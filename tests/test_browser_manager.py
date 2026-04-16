from __future__ import annotations

import asyncio

import pytest

import octopal.browser.manager as browser_manager


class _ChromiumLaunchStub:
    async def launch(self, headless: bool = True):
        assert headless is True
        raise RuntimeError("Executable doesn't exist at /.cache/ms-playwright/chromium/chrome")


class _PlaywrightStartStub:
    def __init__(self) -> None:
        self.chromium = _ChromiumLaunchStub()
        self.stop_calls = 0

    async def stop(self) -> None:
        self.stop_calls += 1


def test_ensure_browser_resets_state_after_launch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = browser_manager.BrowserManager()
    started: list[_PlaywrightStartStub] = []

    class _AsyncPlaywrightFactory:
        async def start(self) -> _PlaywrightStartStub:
            stub = _PlaywrightStartStub()
            started.append(stub)
            return stub

    monkeypatch.setattr(browser_manager, "async_playwright", lambda: _AsyncPlaywrightFactory())

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="Executable doesn't exist"):
            await manager._ensure_browser()
        assert manager._playwright is None
        assert manager._browser is None
        assert manager._contexts == {}
        assert manager._pages == {}
        assert len(started) == 1
        assert started[0].stop_calls == 1

    asyncio.run(scenario())
