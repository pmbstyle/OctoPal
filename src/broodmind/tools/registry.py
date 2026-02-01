from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    permission: str
    scope: str  # "queen" | "worker"
    handler: Callable[[dict[str, Any], dict[str, Any]], str]

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def filter_tools(
    tools: Iterable[ToolSpec],
    *,
    scope: str,
    permissions: dict[str, bool],
) -> list[ToolSpec]:
    available: list[ToolSpec] = []
    for tool in tools:
        if tool.scope != scope:
            continue
        if not permissions.get(tool.permission, False):
            continue
        available.append(tool)
    return available
