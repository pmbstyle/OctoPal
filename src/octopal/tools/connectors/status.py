from __future__ import annotations

import json
from typing import Any

from octopal.infrastructure.config.settings import load_settings
from octopal.tools.registry import ToolSpec


def _resolve_connector_manager(ctx: dict[str, Any]):
    octo = (ctx or {}).get("octo")
    if octo is not None and getattr(octo, "connector_manager", None) is not None:
        return octo.connector_manager

    from octopal.infrastructure.connectors.manager import ConnectorManager

    settings = load_settings()
    return ConnectorManager(
        config=settings.connectors,
        mcp_manager=None,
        octo_config=settings.config_obj,
    )


async def connector_status_read(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    """Return read-only connector availability and auth state."""
    manager = _resolve_connector_manager(ctx)
    statuses = await manager.get_all_statuses()
    requested_name = str((args or {}).get("name", "") or "").strip().lower()
    if requested_name:
        filtered = {requested_name: statuses.get(requested_name, {"status": "unknown_connector"})}
    else:
        filtered = statuses
    return json.dumps({"connectors": filtered}, ensure_ascii=False, indent=2)


def get_connector_status_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="connector_status",
            description=(
                "Read the current status of configured connectors and their enabled services. "
                "Use this to verify whether Gmail or another connector-backed capability is available "
                "before promising access."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional connector name to inspect, for example 'google'.",
                    }
                },
                "additionalProperties": False,
            },
            permission="service_read",
            handler=connector_status_read,
            is_async=True,
        )
    ]
