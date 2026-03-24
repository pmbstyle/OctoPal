from __future__ import annotations

import json

import octopal.tools.web.fetch as fetch_mod
import octopal.tools.web.search as search_mod


def test_web_search_returns_structured_error_when_query_missing() -> None:
    payload = json.loads(search_mod.web_search({}))

    assert payload["ok"] is False
    assert payload["source"] == "brave_search"
    assert payload["error"] == "query is required"


def test_web_search_success_uses_normalized_contract(monkeypatch) -> None:
    class _ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "web": {
                    "results": [
                        {
                            "title": "Octopal",
                            "url": "https://example.com",
                            "description": "Agent runtime",
                            "age": "1 day ago",
                        }
                    ]
                }
            }

    class _ClientStub:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            return _ResponseStub()

    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    monkeypatch.setattr(search_mod.httpx, "Client", _ClientStub)

    payload = json.loads(search_mod.web_search({"query": "Octopal"}))

    assert payload["ok"] is True
    assert payload["source"] == "brave_search"
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "Octopal"


def test_web_fetch_returns_structured_error_when_url_missing() -> None:
    payload = json.loads(fetch_mod.web_fetch({}))

    assert payload["ok"] is False
    assert payload["source"] == "web_fetch"
    assert payload["error"] == "url is required"


def test_web_fetch_success_uses_normalized_contract(monkeypatch) -> None:
    class _ResponseStub:
        status_code = 200
        text = "<html><body><h1>Hello</h1><p>world</p></body></html>"
        headers = {"content-type": "text/html"}

    class _ClientStub:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, *args, **kwargs):
            return _ResponseStub()

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr(fetch_mod.httpx, "Client", _ClientStub)

    payload = json.loads(fetch_mod.web_fetch({"url": "https://example.com"}))

    assert payload["ok"] is True
    assert payload["source"] == "basic_fetch"
    assert payload["url"] == "https://example.com"
    assert "Hello" in payload["snippet"]
