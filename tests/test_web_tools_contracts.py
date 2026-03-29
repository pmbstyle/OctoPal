from __future__ import annotations

import json

import octopal.tools.web.fetch as fetch_mod
import octopal.tools.web.search as search_mod


def test_web_search_returns_structured_error_when_query_missing() -> None:
    payload = json.loads(search_mod.web_search({}))

    assert payload["ok"] is False
    assert payload["source"] == "web_search"
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
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr("octopal.tools.web.providers.brave_provider.httpx.Client", _ClientStub)

    payload = json.loads(search_mod.web_search({"query": "Octopal"}))

    assert payload["ok"] is True
    assert payload["source"] == "brave_search"
    assert payload["provider"] == "brave"
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "Octopal"


def test_web_search_can_use_firecrawl_provider(monkeypatch) -> None:
    class _ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "web": [
                        {
                            "title": "Firecrawl result",
                            "url": "https://example.com/fc",
                            "description": "Search via Firecrawl",
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

        def post(self, *args, **kwargs):
            return _ResponseStub()

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setattr("octopal.tools.web.providers.firecrawl_provider.httpx.Client", _ClientStub)

    payload = json.loads(search_mod.web_search({"query": "Octopal", "provider": "firecrawl"}))

    assert payload["ok"] is True
    assert payload["source"] == "firecrawl_search"
    assert payload["provider"] == "firecrawl"
    assert payload["results"][0]["title"] == "Firecrawl result"


def test_web_search_auto_falls_back_to_firecrawl_when_brave_missing(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    def _fake_run_search(args):
        assert args["query"] == "Octopal"
        return {
            "ok": True,
            "source": "firecrawl_search",
            "provider": "firecrawl",
            "query": "Octopal",
            "count": 0,
            "results": [],
            "degraded": False,
            "fallback_used": False,
            "rate_limited": False,
        }

    monkeypatch.setattr(search_mod, "run_search", _fake_run_search)

    payload = json.loads(search_mod.web_search({"query": "Octopal"}))

    assert payload["ok"] is True
    assert payload["provider"] == "firecrawl"


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


def test_markdown_new_fetch_normalizes_json_envelope(monkeypatch) -> None:
    class _ResponseStub:
        status_code = 200
        text = json.dumps(
            {
                "success": True,
                "title": "Example Domain",
                "content": "# Example Domain\n\nBody",
            }
        )
        headers = {"content-type": "application/json; charset=utf-8"}

    class _ClientStub:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return _ResponseStub()

    monkeypatch.setattr(fetch_mod.httpx, "Client", _ClientStub)

    payload = json.loads(fetch_mod.markdown_new_fetch({"url": "https://example.com"}))

    assert payload["ok"] is True
    assert payload["source"] == "markdown.new"
    assert payload["content_type"] == "text/markdown"
    assert payload["raw_content_type"] == "application/json; charset=utf-8"
    assert payload["title"] == "Example Domain"
    assert payload["snippet"].startswith("# Example Domain")
