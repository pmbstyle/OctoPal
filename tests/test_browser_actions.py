from __future__ import annotations

import asyncio

import octopal.tools.browser.actions as browser_actions


class _LocatorStub:
    def __init__(self, text: str = "", should_fail: bool = False) -> None:
        self._text = text
        self._should_fail = should_fail
        self.wait_calls: list[tuple[str, int]] = []

    def nth(self, _index: int):
        return self

    @property
    def first(self):
        return self

    async def wait_for(self, *, state: str, timeout: int) -> None:
        self.wait_calls.append((state, timeout))
        if self._should_fail:
            raise RuntimeError("missing")

    async def inner_text(self, timeout: int = 5000) -> str:
        if self._should_fail:
            raise RuntimeError("cannot extract")
        return self._text


class _PageStub:
    def __init__(self) -> None:
        self.url = "https://example.com/page"
        self.refs = {
            ("button", "Save", True): _LocatorStub(text="Save"),
        }
        self.text_locator = _LocatorStub()
        self.body_locator = _LocatorStub(text="Page body content")

    def get_by_role(self, role: str, name: str | None = None, exact: bool = False):
        return self.refs[(role, name, exact)]

    def get_by_text(self, text: str, exact: bool = False):
        assert text == "Done"
        assert exact is False
        return self.text_locator

    def locator(self, selector: str):
        assert selector == "body"
        return self.body_locator

    async def title(self) -> str:
        return "Example title"


class _ManagerStub:
    def __init__(self, page: _PageStub) -> None:
        self._page = page

    async def get_page(self, chat_id: int):
        assert chat_id == 7
        return self._page


def test_browser_wait_for_uses_text_lookup(monkeypatch) -> None:
    page = _PageStub()
    monkeypatch.setattr(browser_actions, "get_browser_manager", lambda: _ManagerStub(page))

    async def scenario() -> None:
        result = await browser_actions.browser_wait_for(
            {"text": "Done", "state": "visible", "timeout_ms": 1234},
            {"chat_id": 7},
        )
        assert result == "Text appeared: Done"
        assert page.text_locator.wait_calls == [("visible", 1234)]

    asyncio.run(scenario())


def test_browser_extract_returns_page_summary(monkeypatch) -> None:
    page = _PageStub()
    monkeypatch.setattr(browser_actions, "get_browser_manager", lambda: _ManagerStub(page))

    async def scenario() -> None:
        result = await browser_actions.browser_extract({"max_chars": 500}, {"chat_id": 7})
        assert result["ok"] is True
        assert result["source"] == "page"
        assert result["title"] == "Example title"
        assert result["text"] == "Page body content"

    asyncio.run(scenario())


def test_browser_extract_can_use_snapshot_ref(monkeypatch) -> None:
    page = _PageStub()
    monkeypatch.setattr(browser_actions, "get_browser_manager", lambda: _ManagerStub(page))
    monkeypatch.setattr(
        browser_actions,
        "_SESSION_REFS",
        {7: {"e1": {"role": "button", "name": "Save", "nth": 0}}},
    )

    async def scenario() -> None:
        result = await browser_actions.browser_extract({"ref": "e1"}, {"chat_id": 7})
        assert result == {"ok": True, "source": "ref", "ref": "e1", "text": "Save"}

    asyncio.run(scenario())


def test_browser_workflow_sequences_existing_actions(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _open(args, ctx):
        del ctx
        calls.append(("open", dict(args)))
        return "Successfully opened https://example.com"

    async def _wait_for(args, ctx):
        del ctx
        calls.append(("wait_for", dict(args)))
        return "Text appeared: Done"

    async def _extract(args, ctx):
        del ctx
        calls.append(("extract", dict(args)))
        return {"ok": True, "source": "page", "text": "Workflow body"}

    monkeypatch.setattr(browser_actions, "browser_open", _open)
    monkeypatch.setattr(browser_actions, "browser_wait_for", _wait_for)
    monkeypatch.setattr(browser_actions, "browser_extract", _extract)
    monkeypatch.setattr(
        browser_actions,
        "_WORKFLOW_ACTIONS",
        {
            "open": _open,
            "wait_for": _wait_for,
            "extract": _extract,
        },
    )

    async def scenario() -> None:
        result = await browser_actions.browser_workflow(
            {
                "steps": [
                    {"action": "open", "url": "https://example.com"},
                    {"action": "wait_for", "text": "Done"},
                    {"action": "extract", "max_chars": 200},
                ]
            },
            {"chat_id": 7},
        )
        assert result["ok"] is True
        assert result["step_count"] == 3
        assert [step["action"] for step in result["steps"]] == ["open", "wait_for", "extract"]
        assert result["steps"][2]["text"] == "Workflow body"
        assert calls == [
            ("open", {"url": "https://example.com"}),
            ("wait_for", {"text": "Done"}),
            ("extract", {"max_chars": 200}),
        ]

    asyncio.run(scenario())
