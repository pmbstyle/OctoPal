from __future__ import annotations

import json
from types import SimpleNamespace

from broodmind.tools.mcp.management import mcp_discover


class _MCPStub:
    def __init__(self) -> None:
        self._tools = {
            "docs": [
                SimpleNamespace(
                    name="mcp_docs_search_docs",
                    remote_tool_name="search_docs",
                    description="Search the documentation corpus.",
                )
            ],
            "github": [],
        }

    def get_server_statuses(self):
        return {
            "docs": {
                "name": "Docs",
                "status": "connected",
                "connected": True,
                "reason": "1 tool(s) available",
                "transport": "sse",
            },
            "github": {
                "name": "GitHub",
                "status": "error",
                "connected": False,
                "reason": "auth expired",
                "transport": "streamable-http",
            },
        }


class _QueenStub:
    def __init__(self) -> None:
        self.mcp_manager = _MCPStub()


def test_mcp_discover_summarizes_ready_and_unavailable_servers() -> None:
    payload = json.loads(mcp_discover({}, {"queen": _QueenStub()}))

    assert payload["status"] == "ok"
    assert payload["server_count"] == 2
    assert payload["connected_count"] == 1
    docs = next(server for server in payload["servers"] if server["server_id"] == "docs")
    github = next(server for server in payload["servers"] if server["server_id"] == "github")

    assert docs["suggested_action"] == "call_tool_directly"
    assert docs["tools"][0]["generated_name"] == "mcp_docs_search_docs"
    assert "mcp_call" in docs["tools"][0]["direct_call_hint"]
    assert github["suggested_action"] == "inspect_connection_error"
    assert any("prefer direct generated tool calls" in hint for hint in payload["hints"])


def test_mcp_discover_can_focus_on_one_server() -> None:
    payload = json.loads(mcp_discover({"server_id": "docs"}, {"queen": _QueenStub()}))

    assert payload["server_count"] == 1
    assert payload["servers"][0]["server_id"] == "docs"
