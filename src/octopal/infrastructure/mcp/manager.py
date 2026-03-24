from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from octopal.runtime.tool_errors import MCPToolCallError

if TYPE_CHECKING:
    from octopal.tools.registry import ToolSpec


@dataclass
class MCPServerConfig:
    id: str
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    transport: Literal["auto", "sse", "streamable-http", "stdio"] | None = None
    last_error: str | None = None

logger = structlog.get_logger(__name__)
_MCP_PERMANENT_ERROR_THRESHOLD = 2
_MCP_PERMANENT_ERROR_OPEN_SECONDS = 300.0
_MCP_TRANSIENT_ERROR_THRESHOLD = 5
_MCP_TRANSIENT_ERROR_OPEN_SECONDS = 60.0
_MCP_DEFAULT_TIMEOUT_SECONDS = 120.0
_MCP_SLOW_TIMEOUT_SECONDS = 300.0
_MCP_RECONNECT_BASE_SECONDS = 2.0
_MCP_RECONNECT_MAX_SECONDS = 60.0
_MCP_RETRYABLE_CLASSIFICATIONS = {
    "timeout",
    "rate_limited",
    "upstream_5xx",
    "unknown_error",
}
_MCP_SLOW_TOOL_HINTS = (
    "search",
    "fetch",
    "crawl",
    "thread",
    "inbox",
    "mail",
    "list_",
    "query",
)

class MCPManager:
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.sessions: dict[str, ClientSession] = {}
        # Stores the background task that keeps the session alive
        self._tasks: dict[str, asyncio.Task] = {}
        # Communication queues for disconnect signals
        self._stop_events: dict[str, asyncio.Event] = {}
        self._tools: dict[str, list[ToolSpec]] = {}
        self._server_configs: dict[str, MCPServerConfig] = {}
        self._tool_failure_state: dict[tuple[str, str], dict[str, Any]] = {}
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._reconnect_attempts: dict[str, int] = {}
        self._manual_disconnects: set[str] = set()
        self._shutdown_requested = False
        self.config_path = workspace_dir / "mcp_servers.json"
        self._configs_loaded = False

    def _load_configs_from_disk(self) -> dict[str, MCPServerConfig]:
        if self._configs_loaded:
            return dict(self._server_configs)
        if not self.config_path.exists():
            self._configs_loaded = True
            return dict(self._server_configs)

        config_data = json.loads(self.config_path.read_text(encoding="utf-8"))
        loaded: dict[str, MCPServerConfig] = {}
        for server_id, cfg in config_data.items():
            existing = self._server_configs.get(server_id)
            loaded[server_id] = MCPServerConfig(
                id=server_id,
                name=cfg.get("name", server_id),
                command=cfg.get("command"),
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
                url=cfg.get("url"),
                headers=cfg.get("headers", {}),
                transport=_normalize_transport(cfg.get("transport") or cfg.get("type")),
                last_error=existing.last_error if existing else None,
            )
        self._server_configs.update(loaded)
        self._configs_loaded = True
        return dict(self._server_configs)

    async def load_and_connect_all(self):
        if not self.config_path.exists():
            return
        try:
            for server_id, mcp_cfg in self._load_configs_from_disk().items():
                try:
                    await self.connect_server(mcp_cfg)
                except Exception:
                    logger.exception("Failed to connect to MCP server on startup", server_id=server_id)
        except Exception:
            logger.exception("Failed to load MCP config")

    async def ensure_configured_servers_connected(
        self,
        server_ids: list[str] | None = None,
    ) -> dict[str, str]:
        """Reconnect configured MCP servers that should already be available."""
        try:
            configs = self._load_configs_from_disk()
        except Exception:
            logger.exception("Failed to load MCP config for ensure_configured_servers_connected")
            return {}

        requested_ids = [str(server_id).strip() for server_id in (server_ids or []) if str(server_id).strip()]
        target_ids = requested_ids or list(configs.keys())
        results: dict[str, str] = {}
        for server_id in target_ids:
            cfg = configs.get(server_id)
            if cfg is None:
                results[server_id] = "unknown"
                continue
            if server_id in self.sessions:
                results[server_id] = "connected"
                continue
            try:
                await self.connect_server(cfg)
                results[server_id] = "connected"
            except Exception as exc:
                cfg.last_error = str(exc)
                results[server_id] = "error"
                logger.warning(
                    "Failed to ensure configured MCP server is connected",
                    server_id=server_id,
                    error=str(exc),
                )
        return results

    async def connect_server(self, config: MCPServerConfig) -> list[ToolSpec]:
        self._shutdown_requested = False
        self._server_configs[config.id] = config
        self._manual_disconnects.discard(config.id)
        reconnect_task = self._reconnect_tasks.pop(config.id, None)
        if reconnect_task and not reconnect_task.done():
            reconnect_task.cancel()
        if config.id in self.sessions:
            logger.info("MCP server already connected", server_id=config.id)
            return self._tools.get(config.id, [])

        # Create an event to signal connection readiness and an event for stopping
        ready_event = asyncio.Event()
        stop_event = asyncio.Event()
        self._stop_events[config.id] = stop_event

        # Start background task to manage the lifecycle
        task = asyncio.create_task(self._run_server_lifecycle(config, ready_event, stop_event))
        self._tasks[config.id] = task

        # Wait for the session to be initialized or task to fail
        try:
            # Monitor both the ready event and the task itself
            done, pending = await asyncio.wait(
                [asyncio.create_task(ready_event.wait()), task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=45.0
            )

            # Check if we timed out
            if not done:
                for pending_task in pending:
                    pending_task.cancel()
                config.last_error = "Connection timed out after 45s"
                raise RuntimeError(f"Connection to MCP server '{config.id}' timed out after 45s.")

            if ready_event.is_set():
                # Success!
                config.last_error = None
                self._reconnect_attempts.pop(config.id, None)
                return self._tools.get(config.id, [])

            # If the task finished but ready_event is not set, it failed
            if task in done:
                exc = task.exception()
                if exc:
                    config.last_error = str(exc)
                    raise exc
                config.last_error = "Exited unexpectedly"
                raise RuntimeError(f"MCP server task '{config.id}' exited unexpectedly.")

            config.last_error = "Failed (unknown state)"
            raise RuntimeError(f"Connection to MCP server '{config.id}' failed (unknown state).")

        except Exception as e:
            logger.error("Failed to connect to MCP server", server_id=config.id, error=str(e))
            if not config.last_error:
                config.last_error = str(e)
            await self.disconnect_server(config.id, intentional=False)
            if isinstance(e, RuntimeError) and "timed out" in str(e):
                raise
            raise RuntimeError(f"MCP Connection Error ({config.id}): {e}") from e

    async def _run_server_lifecycle(self, config: MCPServerConfig, ready_event: asyncio.Event, stop_event: asyncio.Event):
        """Manages the lifetime of a single MCP server connection."""
        from contextlib import AsyncExitStack
        exit_stack = AsyncExitStack()

        try:
            selected_transport = _resolve_transport(config)
            if selected_transport == "sse":
                logger.info("Establishing MCP SSE transport", server_id=config.id, url=config.url)
                read_stream, write_stream = await exit_stack.enter_async_context(
                    sse_client(url=config.url or "", headers=config.headers)
                )
            elif selected_transport == "streamable-http":
                logger.info("Establishing MCP streamable-http transport", server_id=config.id, url=config.url)
                read_stream, write_stream, _get_session_id = await exit_stack.enter_async_context(
                    streamablehttp_client(
                        url=config.url or "",
                        headers=config.headers or None,
                        timeout=timedelta(seconds=30),
                        sse_read_timeout=timedelta(seconds=300),
                    )
                )
            elif selected_transport == "stdio":
                logger.info("Establishing MCP stdio transport", server_id=config.id, command=config.command)
                params = StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    env={**config.env, "PATH": os.environ.get("PATH", "")} if config.env else None
                )
                read_stream, write_stream = await exit_stack.enter_async_context(stdio_client(params))
            else:
                raise ValueError(f"Unsupported MCP transport '{selected_transport}' for server {config.id}.")

            logger.info("Initializing MCP session", server_id=config.id)
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))

            await session.initialize()
            self.sessions[config.id] = session

            # Fetch tools
            logger.info("Fetching tools from MCP server", server_id=config.id)
            mcp_tools_list = await session.list_tools()

            specs = []
            from octopal.tools.registry import ToolSpec

            for tool in mcp_tools_list.tools:
                # Normalize tool name: replace dashes with underscores for better LLM compatibility
                safe_id = config.id.replace("-", "_")
                safe_tool_name = tool.name.replace("-", "_")
                mcp_tool_name = f"mcp_{safe_id}_{safe_tool_name}"

                spec = ToolSpec(
                    name=mcp_tool_name,
                    description=f"[MCP Tool from {config.name}] {tool.description}. Call this tool directly by using the name '{mcp_tool_name}' in your tool call block.",
                    parameters=tool.inputSchema,
                    permission="mcp_exec",
                    handler=self._generate_handler(config.id, tool.name),
                    is_async=True,
                    server_id=config.id,
                    remote_tool_name=tool.name,
                )
                specs.append(spec)

            self._tools[config.id] = specs
            logger.info("MCP server connected and tools ready", server_id=config.id, tool_count=len(specs))

            # Signal that we are ready
            ready_event.set()

            # Keep alive until signaled to stop
            await stop_event.wait()
            logger.info("Shutting down MCP server session (signaled)", server_id=config.id)

        except Exception as e:
            hint = _connection_hint(e)
            logger.exception("MCP server lifecycle error", server_id=config.id, transport=config.transport or "auto", hint=hint)
            if not ready_event.is_set():
                # Task failed before becoming ready - signal the waiter with an error if possible
                # But here we just let the waiter catch the fact that ready_event was never set.
                pass
        finally:
            # Clean up
            self.sessions.pop(config.id, None)
            self._tools.pop(config.id, None)
            self._tasks.pop(config.id, None)
            self._stop_events.pop(config.id, None)

            # Closing the stack will close the context managers (stdio/sse clients)
            # This happens in the same task that created them, which anyio requires.
            await exit_stack.aclose()
            logger.info("MCP server resources released", server_id=config.id)
            if (
                not self._shutdown_requested
                and config.id not in self._manual_disconnects
                and config.id in self._server_configs
                and config.id not in self.sessions
            ):
                self._schedule_reconnect(config.id)

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        args: dict[str, Any],
        *,
        allow_name_fallback: bool = False,
    ) -> Any:
        session = self.sessions.get(server_id)
        if not session:
            raise RuntimeError(f"MCP session '{server_id}' is not active.")

        tool_candidates = [tool_name]
        alt_name = _alternate_tool_name(tool_name) if allow_name_fallback else None
        if alt_name:
            tool_candidates.append(alt_name)

        timeout_seconds = _mcp_timeout_seconds(tool_name, args)
        last_exc: Exception | None = None
        for index, candidate_name in enumerate(tool_candidates):
            state_key = (server_id, candidate_name)
            now = time.monotonic()
            state = self._tool_failure_state.get(state_key)
            if state and float(state.get("open_until", 0.0)) > now:
                remaining = max(1, int(float(state["open_until"]) - now))
                last_class = str(state.get("classification", "unknown"))
                raise MCPToolCallError(
                    classification=last_class,
                    hint="Previous failures keep this MCP tool circuit open.",
                    retryable=_is_retryable_mcp_classification(last_class),
                    server_id=server_id,
                    tool_name=candidate_name,
                    message=(
                        f"MCP tool '{candidate_name}' on '{server_id}' is temporarily paused for {remaining}s "
                        f"after repeated '{last_class}' failures. Try a fallback path or a different tool."
                    ),
                    details={"cooldown_seconds": remaining, "circuit_open": True},
                )

            try:
                result = await asyncio.wait_for(
                    session.call_tool(candidate_name, arguments=args),
                    timeout=timeout_seconds,
                )
                self._tool_failure_state.pop(state_key, None)
                if index > 0:
                    logger.warning(
                        "MCP tool name fallback succeeded",
                        server_id=server_id,
                        requested_tool=tool_name,
                        resolved_tool=candidate_name,
                    )
                return result
            except TimeoutError:
                last_exc = RuntimeError(
                    f"MCP call timed out after {int(timeout_seconds)}s for '{candidate_name}' on '{server_id}'."
                )
                exc_to_classify: Exception = last_exc
            except Exception as exc:
                last_exc = exc
                exc_to_classify = exc
                if (
                    index == 0
                    and len(tool_candidates) > 1
                    and _is_tool_not_found_error(exc)
                ):
                    logger.warning(
                        "Retrying MCP call with alternate tool name",
                        server_id=server_id,
                        requested_tool=tool_name,
                        alternate_tool=tool_candidates[1],
                    )
                    continue

            error_info = _classify_mcp_call_error(exc_to_classify)
            entry = self._tool_failure_state.get(
                state_key,
                {"count": 0, "open_until": 0.0, "classification": error_info["classification"]},
            )
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["classification"] = error_info["classification"]
            entry["last_error"] = str(exc_to_classify)

            if error_info["retryable"]:
                if entry["count"] >= _MCP_TRANSIENT_ERROR_THRESHOLD:
                    entry["open_until"] = now + _MCP_TRANSIENT_ERROR_OPEN_SECONDS
            else:
                if entry["count"] >= _MCP_PERMANENT_ERROR_THRESHOLD:
                    entry["open_until"] = now + _MCP_PERMANENT_ERROR_OPEN_SECONDS

            self._tool_failure_state[state_key] = entry

            if float(entry.get("open_until", 0.0)) > now:
                logger.warning(
                    "Opened MCP tool circuit after repeated failures",
                    server_id=server_id,
                    tool=tool_name,
                    classification=error_info["classification"],
                    cooldown_seconds=int(float(entry["open_until"]) - now),
                    failure_count=entry["count"],
                )

            raise MCPToolCallError(
                classification=str(error_info["classification"]),
                hint=str(error_info["hint"]),
                retryable=bool(error_info["retryable"]),
                server_id=server_id,
                tool_name=candidate_name,
            ) from exc_to_classify

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"MCP call failed for '{tool_name}' on '{server_id}'")

    def _generate_handler(self, server_id: str, tool_name: str):
        async def handler(args: dict[str, Any], ctx: dict[str, Any]) -> Any:
            worker = ctx.get("worker")
            if worker:
                logger.info("Worker requesting MCP tool call", server_id=server_id, tool=tool_name)
                try:
                    result = await worker.call_mcp_tool(server_id, tool_name, args)
                    return result
                except Exception as e:
                    return f"Error calling MCP tool via proxy: {e}"

            session = self.sessions.get(server_id)
            if not session:
                return f"Error: MCP session {server_id} not active."

            logger.info("Calling MCP tool", server_id=server_id, tool=tool_name)
            try:
                result = await self.call_tool(server_id, tool_name, args)
                return [c.model_dump() if hasattr(c, "model_dump") else str(c) for c in result.content]
            except Exception as e:
                logger.exception("MCP tool call failed", server_id=server_id, tool=tool_name)
                return {
                    "ok": False,
                    "error": str(e),
                    "server_id": server_id,
                    "tool": tool_name,
                }

        return handler

    def _schedule_reconnect(self, server_id: str) -> None:
        if self._shutdown_requested or server_id in self._manual_disconnects:
            return
        existing = self._reconnect_tasks.get(server_id)
        if existing and not existing.done():
            return
        config = self._server_configs.get(server_id)
        if config is None:
            return
        attempt = int(self._reconnect_attempts.get(server_id, 0)) + 1
        self._reconnect_attempts[server_id] = attempt
        delay = min(_MCP_RECONNECT_MAX_SECONDS, _MCP_RECONNECT_BASE_SECONDS * (2 ** (attempt - 1)))

        async def _reconnect() -> None:
            try:
                logger.warning(
                    "Scheduling MCP reconnect",
                    server_id=server_id,
                    attempt=attempt,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)
                if self._shutdown_requested or server_id in self._manual_disconnects or server_id in self.sessions:
                    return
                await self.connect_server(config)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "MCP reconnect attempt failed",
                    server_id=server_id,
                    attempt=attempt,
                    exc_info=True,
                )
                self._schedule_reconnect(server_id)
            finally:
                task = self._reconnect_tasks.get(server_id)
                if task is asyncio.current_task():
                    self._reconnect_tasks.pop(server_id, None)

        self._reconnect_tasks[server_id] = asyncio.create_task(_reconnect())

    async def disconnect_server(self, server_id: str, *, intentional: bool = True):
        if intentional:
            self._manual_disconnects.add(server_id)
        reconnect_task = self._reconnect_tasks.pop(server_id, None)
        if reconnect_task and not reconnect_task.done():
            reconnect_task.cancel()
        event = self._stop_events.get(server_id)
        if event:
            event.set()

        task = self._tasks.get(server_id)
        if task:
            try:
                # Wait for cleanup to finish
                await asyncio.wait_for(task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                if not task.done():
                    task.cancel()
            logger.info("Disconnected MCP server", server_id=server_id)

    def get_all_tools(self) -> list[ToolSpec]:
        all_specs = []
        for specs in self._tools.values():
            all_specs.extend(specs)
        return all_specs

    async def shutdown(self):
        self._shutdown_requested = True
        for task in list(self._reconnect_tasks.values()):
            if not task.done():
                task.cancel()
        self._reconnect_tasks.clear()
        # Trigger all stop events
        for server_id in list(self._stop_events.keys()):
            await self.disconnect_server(server_id)

    def get_server_statuses(self) -> dict[str, dict[str, Any]]:
        statuses = {}
        for server_id, config in self._server_configs.items():
            is_connected = server_id in self.sessions
            tools = self._tools.get(server_id, [])
            reconnect_task = self._reconnect_tasks.get(server_id)
            reconnecting = bool(reconnect_task and not reconnect_task.done())
            reconnect_attempts = int(self._reconnect_attempts.get(server_id, 0))
            if is_connected:
                status = "connected"
                reason = f"{len(tools)} tool(s) available"
            elif reconnecting:
                status = "reconnecting"
                reason = "Background reconnect scheduled"
            elif config.last_error:
                status = "error"
                reason = str(config.last_error)
            else:
                status = "configured"
                reason = "Configured but not connected"
            statuses[server_id] = {
                "name": config.name,
                "status": status,
                "configured": True,
                "connected": is_connected,
                "reconnecting": reconnecting,
                "reason": reason,
                "tool_count": len(tools),
                "error": config.last_error,
                "transport": config.transport or "auto",
                "reconnect_attempts": reconnect_attempts,
                "manual_disconnect": server_id in self._manual_disconnects,
            }
        return statuses


def _normalize_transport(raw: Any) -> Literal["auto", "sse", "streamable-http", "stdio"] | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in {"auto", ""}:
        return "auto"
    if value in {"sse", "http-sse"}:
        return "sse"
    if value in {"streamable-http", "streamable_http", "streamablehttp", "http"}:
        return "streamable-http"
    if value in {"stdio", "local"}:
        return "stdio"
    return None


def _resolve_transport(config: MCPServerConfig) -> Literal["sse", "streamable-http", "stdio"]:
    normalized = _normalize_transport(config.transport) or "auto"
    if normalized != "auto":
        return normalized
    if config.command:
        return "stdio"
    if config.url:
        url = config.url.lower()
        if "streamable" in url:
            return "streamable-http"
        return "sse"
    raise ValueError(f"MCP server {config.id} must have either 'command' or 'url'.")


def _connection_hint(error: Exception) -> str:
    text = str(error).lower()
    if "text/event-stream" in text and "application/json" in text:
        return "Transport mismatch: server returned JSON, but client expected SSE. Try transport='streamable-http'."
    if "404" in text or "not found" in text:
        return "Endpoint not found: verify MCP URL/path and provider docs."
    if "timed out" in text:
        return "Connection timed out: check network egress, DNS, firewall, or provider availability."
    if "connection closed" in text:
        return "Remote side closed connection early: verify auth and protocol compatibility."
    return "Unknown MCP connection issue. Verify URL/transport/auth."


def _classify_mcp_call_error(error: Exception) -> dict[str, Any]:
    text = str(error).lower()
    if "invalid arguments for tool" in text:
        missing_fields = _extract_mcp_missing_argument_names(str(error))
        field_suffix = ""
        if missing_fields:
            field_suffix = f" Missing required fields: {', '.join(missing_fields)}."
        return {
            "classification": "invalid_arguments",
            "retryable": False,
            "hint": (
                "Remote MCP server rejected the tool arguments before execution."
                f"{field_suffix}"
            ),
        }
    if "invalid tools/call result" in text or "structuredcontent" in text:
        return {
            "classification": "schema_mismatch",
            "retryable": False,
            "hint": "Remote MCP response schema is incompatible (structuredContent is invalid).",
        }
    if "unknown tool" in text or "not found" in text:
        return {
            "classification": "tool_not_found",
            "retryable": False,
            "hint": "Tool name mismatch between Octopal and remote MCP server.",
        }
    if "timeout" in text or "timed out" in text:
        return {
            "classification": "timeout",
            "retryable": True,
            "hint": "Remote MCP call timed out; retry may succeed.",
        }
    if "429" in text or "rate limit" in text:
        return {
            "classification": "rate_limited",
            "retryable": True,
            "hint": "Remote MCP server is rate-limiting requests.",
        }
    if "500" in text or "502" in text or "503" in text:
        return {
            "classification": "upstream_5xx",
            "retryable": True,
            "hint": "Remote MCP server/upstream returned a temporary server error.",
        }
    return {
        "classification": "unknown_error",
        "retryable": True,
        "hint": "MCP call failed with an unclassified error.",
    }


def _extract_mcp_missing_argument_names(error_text: str) -> list[str]:
    matches = re.findall(r'"path"\s*:\s*\[\s*"([^"]+)"\s*\]', error_text, flags=re.IGNORECASE)
    unique: list[str] = []
    for match in matches:
        name = str(match).strip()
        if name and name not in unique:
            unique.append(name)
    return unique


def _is_retryable_mcp_classification(classification: str) -> bool:
    return classification in _MCP_RETRYABLE_CLASSIFICATIONS


def _alternate_tool_name(tool_name: str) -> str | None:
    if "_" in tool_name:
        alt = tool_name.replace("_", "-")
        return alt if alt != tool_name else None
    if "-" in tool_name:
        alt = tool_name.replace("-", "_")
        return alt if alt != tool_name else None
    return None


def _is_tool_not_found_error(error: Exception) -> bool:
    text = str(error).lower()
    return "unknown tool" in text or "not found" in text


def _mcp_timeout_seconds(tool_name: str, args: dict[str, Any]) -> float:
    if isinstance(args, dict):
        explicit = args.get("timeout_seconds")
        if explicit is not None:
            try:
                value = float(explicit)
                if value > 0:
                    return max(5.0, min(value, 600.0))
            except Exception:
                pass
    lowered = tool_name.lower()
    if any(hint in lowered for hint in _MCP_SLOW_TOOL_HINTS):
        return _MCP_SLOW_TIMEOUT_SECONDS
    return _MCP_DEFAULT_TIMEOUT_SECONDS
