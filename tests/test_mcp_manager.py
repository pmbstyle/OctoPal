from __future__ import annotations

import asyncio

from broodmind.infrastructure.mcp.manager import MCPManager, MCPServerConfig, _classify_mcp_call_error


def test_mcp_manager_schedules_self_healing_reconnect(tmp_path, monkeypatch) -> None:
    manager = MCPManager(tmp_path)
    manager._server_configs["demo"] = MCPServerConfig(
        id="demo",
        name="Demo",
        command="demo-cmd",
        transport="stdio",
    )

    calls: list[str] = []

    async def _fake_connect(config: MCPServerConfig):
        calls.append(config.id)
        return []

    monkeypatch.setattr("broodmind.infrastructure.mcp.manager._MCP_RECONNECT_BASE_SECONDS", 0.01)
    monkeypatch.setattr("broodmind.infrastructure.mcp.manager._MCP_RECONNECT_MAX_SECONDS", 0.01)
    manager.connect_server = _fake_connect  # type: ignore[method-assign]

    async def scenario():
        manager._schedule_reconnect("demo")
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert calls == ["demo"]


def test_mcp_manager_does_not_reconnect_after_intentional_disconnect(tmp_path, monkeypatch) -> None:
    manager = MCPManager(tmp_path)
    manager._server_configs["demo"] = MCPServerConfig(
        id="demo",
        name="Demo",
        command="demo-cmd",
        transport="stdio",
    )

    calls: list[str] = []

    async def _fake_connect(config: MCPServerConfig):
        calls.append(config.id)
        return []

    monkeypatch.setattr("broodmind.infrastructure.mcp.manager._MCP_RECONNECT_BASE_SECONDS", 0.01)
    monkeypatch.setattr("broodmind.infrastructure.mcp.manager._MCP_RECONNECT_MAX_SECONDS", 0.01)
    manager.connect_server = _fake_connect  # type: ignore[method-assign]

    async def scenario():
        await manager.disconnect_server("demo", intentional=True)
        manager._schedule_reconnect("demo")
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert calls == []


def test_mcp_manager_statuses_report_reconnecting_and_reason(tmp_path) -> None:
    manager = MCPManager(tmp_path)
    manager._server_configs["demo"] = MCPServerConfig(
        id="demo",
        name="Demo",
        command="demo-cmd",
        transport="stdio",
        last_error="socket closed",
    )

    async def _idle() -> None:
        await asyncio.sleep(10)

    async def scenario():
        manager._reconnect_attempts["demo"] = 2
        manager._reconnect_tasks["demo"] = asyncio.create_task(_idle())
        statuses = manager.get_server_statuses()
        task = manager._reconnect_tasks.pop("demo")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return statuses

    statuses = asyncio.run(scenario())
    payload = statuses["demo"]
    assert payload["status"] == "reconnecting"
    assert payload["configured"] is True
    assert payload["connected"] is False
    assert payload["reconnecting"] is True
    assert payload["reason"] == "Background reconnect scheduled"
    assert payload["reconnect_attempts"] == 2


def test_classify_mcp_invalid_arguments_preserves_missing_fields() -> None:
    error = RuntimeError(
        """MCP error -32602: Invalid arguments for tool analyze_image: [
  {
    "code": "invalid_type",
    "expected": "string",
    "received": "undefined",
    "path": [
      "image_source"
    ],
    "message": "Required"
  },
  {
    "code": "invalid_type",
    "expected": "string",
    "received": "undefined",
    "path": [
      "prompt"
    ],
    "message": "Required"
  }
]"""
    )

    info = _classify_mcp_call_error(error)

    assert info["classification"] == "invalid_arguments"
    assert info["retryable"] is False
    assert "image_source" in info["hint"]
    assert "prompt" in info["hint"]


def test_classify_mcp_schema_mismatch_stays_distinct() -> None:
    error = RuntimeError("invalid tools/call result: structuredContent did not match schema")

    info = _classify_mcp_call_error(error)

    assert info["classification"] == "schema_mismatch"
    assert "structuredContent" in info["hint"]
