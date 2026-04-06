from __future__ import annotations

import json
from typing import Any

from octopal.tools.metadata import ToolMetadata
from octopal.tools.registry import ToolSpec

_GMAIL_SERVER_ID = "google-gmail"


def _extract_mcp_payload(result: Any) -> Any:
    content_items = getattr(result, "content", None)
    if not content_items:
        return result

    if len(content_items) == 1:
        item = content_items[0]
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return str(item)

    normalized: list[Any] = []
    for item in content_items:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                normalized.append(json.loads(text))
            except json.JSONDecodeError:
                normalized.append(text)
            continue
        if hasattr(item, "model_dump"):
            normalized.append(item.model_dump())
            continue
        normalized.append(str(item))
    return normalized


def _resolve_mcp_manager(ctx: dict[str, Any], fallback: Any) -> Any:
    octo = (ctx or {}).get("octo")
    if octo is not None and getattr(octo, "mcp_manager", None) is not None:
        return octo.mcp_manager
    return fallback


async def _gmail_mcp_proxy(
    remote_tool_name: str,
    args: dict[str, Any],
    ctx: dict[str, Any],
    *,
    fallback_manager: Any,
) -> Any:
    manager = _resolve_mcp_manager(ctx, fallback_manager)
    if manager is None:
        return {
            "ok": False,
            "error": "Gmail tools are unavailable because no MCP manager is active.",
            "hint": "Restart Octopal after authorizing the Google Gmail connector.",
        }

    try:
        result = await manager.call_tool(
            _GMAIL_SERVER_ID,
            remote_tool_name,
            args or {},
            allow_name_fallback=True,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "server_id": _GMAIL_SERVER_ID,
            "tool": remote_tool_name,
            "hint": "Check connector status and confirm the Gmail MCP server is connected.",
        }

    return _extract_mcp_payload(result)


def _gmail_tool(
    *,
    name: str,
    remote_tool_name: str,
    description: str,
    parameters: dict[str, Any],
    fallback_manager: Any,
    capabilities: tuple[str, ...],
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters=parameters,
        permission="mcp_exec",
        handler=lambda args, ctx, _remote=remote_tool_name, _manager=fallback_manager: _gmail_mcp_proxy(
            _remote,
            args,
            ctx,
            fallback_manager=_manager,
        ),
        is_async=True,
        server_id=_GMAIL_SERVER_ID,
        remote_tool_name=remote_tool_name,
        metadata=ToolMetadata(
            category="connectors",
            risk="safe",
            profile_tags=("research", "communication"),
            capabilities=capabilities,
        ),
    )


def get_gmail_connector_tools(mcp_manager: Any = None) -> list[ToolSpec]:
    if mcp_manager is None:
        return []

    return [
        _gmail_tool(
            name="gmail_get_profile",
            remote_tool_name="get_profile",
            description="Get the connected Gmail account profile. Use this to confirm which mailbox is active.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_list_labels",
            remote_tool_name="list_labels",
            description="List Gmail labels available in the connected mailbox.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_list_messages",
            remote_tool_name="list_messages",
            description=(
                "List recent Gmail messages and return message IDs. Use this first when you need the latest email "
                "or when you do not already have a message ID."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "label_ids": {"type": "array", "items": {"type": "string"}},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 25},
                    "page_token": {"type": "string"},
                    "include_spam_trash": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_search_messages",
            remote_tool_name="search_messages",
            description=(
                "Search Gmail with standard Gmail query syntax and return matching message IDs. "
                "Use this when the user asks for emails by sender, subject, label, or date."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 25},
                    "page_token": {"type": "string"},
                    "include_spam_trash": {"type": "boolean"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_get_message",
            remote_tool_name="get_message",
            description="Read a Gmail message by ID after discovering that ID via gmail_list_messages or gmail_search_messages.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "format": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_batch_get_messages",
            remote_tool_name="batch_get_messages",
            description="Read multiple Gmail messages by ID in one call.",
            parameters={
                "type": "object",
                "properties": {
                    "message_ids": {"type": "array", "items": {"type": "string"}},
                    "format": {"type": "string"},
                },
                "required": ["message_ids"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_get_thread",
            remote_tool_name="get_thread",
            description="Read an entire Gmail thread by thread ID.",
            parameters={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "format": {"type": "string"},
                },
                "required": ["thread_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_get_unread_count",
            remote_tool_name="get_unread_count",
            description="Return the unread email count, optionally scoped to a label such as INBOX.",
            parameters={
                "type": "object",
                "properties": {
                    "label_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_send_message",
            remote_tool_name="send_message",
            description="Send a Gmail message to one or more recipients, optionally attaching it to an existing thread.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "body_text": {"type": "string"},
                    "body_html": {"type": "string"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "thread_id": {"type": "string"},
                },
                "required": ["to", "subject"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_reply_to_message",
            remote_tool_name="reply_to_message",
            description=(
                "Reply to a Gmail message by ID. Use reply_all when the response should include the full original "
                "conversation recipients."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "body_text": {"type": "string"},
                    "body_html": {"type": "string"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                    "bcc": {"type": "array", "items": {"type": "string"}},
                    "reply_all": {"type": "boolean"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_archive_message",
            remote_tool_name="archive_message",
            description="Archive a Gmail message by removing it from Inbox.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_trash_message",
            remote_tool_name="trash_message",
            description="Move a Gmail message to trash.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_delete_message",
            remote_tool_name="delete_message",
            description="Permanently delete a Gmail message.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_mark_message_read",
            remote_tool_name="mark_message_read",
            description="Mark a Gmail message as read.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_mark_message_unread",
            remote_tool_name="mark_message_unread",
            description="Mark a Gmail message as unread.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_modify_message_labels",
            remote_tool_name="modify_message_labels",
            description="Add and/or remove Gmail labels on a message to move it between folders or categories.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "add_label_ids": {"type": "array", "items": {"type": "string"}},
                    "remove_label_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_get_attachment",
            remote_tool_name="get_attachment",
            description="Download a Gmail attachment by message ID and attachment ID.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "attachment_id": {"type": "string"},
                    "filename": {"type": "string"},
                },
                "required": ["message_id", "attachment_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_read", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_add_label_by_name",
            remote_tool_name="add_label_by_name",
            description="Add a Gmail label to a message using a label name or label ID.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "label_name": {"type": "string"},
                },
                "required": ["message_id", "label_name"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_remove_label_by_name",
            remote_tool_name="remove_label_by_name",
            description="Remove a Gmail label from a message using a label name or label ID.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "label_name": {"type": "string"},
                },
                "required": ["message_id", "label_name"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_move_message_to_inbox",
            remote_tool_name="move_message_to_inbox",
            description="Move a Gmail message back into Inbox.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
        _gmail_tool(
            name="gmail_move_message_out_of_inbox",
            remote_tool_name="move_message_out_of_inbox",
            description="Archive a Gmail message by moving it out of Inbox.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                },
                "required": ["message_id"],
                "additionalProperties": False,
            },
            fallback_manager=mcp_manager,
            capabilities=("gmail_write", "connector_use"),
        ),
    ]
