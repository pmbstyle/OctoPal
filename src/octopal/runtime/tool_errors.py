from __future__ import annotations

from typing import Any


class ToolBridgeError(RuntimeError):
    """Structured tool bridge failure that can safely cross worker/runtime boundaries."""

    def __init__(
        self,
        message: str,
        *,
        bridge: str | None = None,
        classification: str | None = None,
        retryable: bool | None = None,
        hint: str | None = None,
        server_id: str | None = None,
        tool_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.bridge = bridge
        self.classification = classification
        self.retryable = retryable
        self.hint = hint
        self.server_id = server_id
        self.tool_name = tool_name
        self.details = dict(details or {})

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "error",
            "message": str(self),
        }
        if self.bridge:
            payload["bridge"] = self.bridge
        if self.classification:
            payload["classification"] = self.classification
        if isinstance(self.retryable, bool):
            payload["retryable"] = self.retryable
        if self.hint:
            payload["hint"] = self.hint
        if self.server_id:
            payload["server_id"] = self.server_id
        if self.tool_name:
            payload["tool_name"] = self.tool_name
        if self.details:
            payload["details"] = dict(self.details)
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        default_bridge: str | None = None,
    ) -> ToolBridgeError:
        details = payload.get("details")
        return cls(
            str(payload.get("message") or "Tool bridge error"),
            bridge=_as_optional_str(payload.get("bridge")) or default_bridge,
            classification=_as_optional_str(payload.get("classification")),
            retryable=payload["retryable"] if isinstance(payload.get("retryable"), bool) else None,
            hint=_as_optional_str(payload.get("hint")),
            server_id=_as_optional_str(payload.get("server_id")),
            tool_name=_as_optional_str(payload.get("tool_name")),
            details=details if isinstance(details, dict) else None,
        )


class MCPToolCallError(ToolBridgeError):
    def __init__(
        self,
        *,
        classification: str,
        hint: str,
        retryable: bool,
        server_id: str,
        tool_name: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message or f"[{classification}] {hint} (server={server_id}, tool={tool_name})",
            bridge="mcp",
            classification=classification,
            retryable=retryable,
            hint=hint,
            server_id=server_id,
            tool_name=tool_name,
            details=details,
        )


def _as_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None
