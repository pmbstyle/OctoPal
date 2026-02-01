from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from broodmind.memory.service import MemoryService
from broodmind.policy.engine import PolicyEngine
from broodmind.providers.base import InferenceProvider, Message
from broodmind.store.base import Store
from broodmind.telegram.approvals import ApprovalManager
from broodmind.workers.contracts import Capability, WorkerResult, WorkerSpec
from broodmind.workers.runtime import WorkerRuntime
from broodmind.tools.registry import ToolSpec, filter_tools
from broodmind.tools.tools import get_tools
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class Queen:
    provider: InferenceProvider
    store: Store
    policy: PolicyEngine
    runtime: WorkerRuntime
    approvals: ApprovalManager
    memory: MemoryService

    async def handle_message(
        self,
        text: str,
        chat_id: int,
        approval_requester=None,
    ) -> "QueenReply":
        logger.info("Queen received message: chat_id=%s len=%s", chat_id, len(text))
        await self.memory.add_message("user", text, {"chat_id": chat_id})
        bootstrap_context = _get_bootstrap_context(self.store, chat_id)
        if _is_list_workers_command(text):
            response = _format_workers_registry(_get_workers_registry())
            await self.memory.add_message("assistant", response, {"chat_id": chat_id})
            if bootstrap_context:
                self.store.mark_chat_bootstrapped(chat_id, _utc_now())
            return QueenReply(immediate=response, followup=None)
        decision = await _route_or_reply(
            self.provider,
            self.memory,
            text,
            chat_id,
            bootstrap_context,
        )
        logger.debug("Queen route decision: delegate=%s", decision.delegate)
        if decision.delegate:
            logger.info("Queen decision: delegate_to_worker=true")
            immediate = decision.reply
            if not immediate:
                logger.info("Queen drafting interim reply (fallback)")
                immediate = await _draft_interim_reply(
                    self.provider,
                    self.memory,
                    text,
                    chat_id,
                    bootstrap_context,
                )
            if decision.task:
                text = decision.task
            await self.memory.add_message("assistant", immediate, {"chat_id": chat_id})
            followup = asyncio.create_task(
                self._run_and_compose_reply(text, chat_id, approval_requester, decision.permissions, decision.lifecycle)
            )
            if bootstrap_context:
                self.store.mark_chat_bootstrapped(chat_id, _utc_now())
            return QueenReply(immediate=immediate, followup=followup)

        logger.info("Queen decision: delegate_to_worker=false")
        await self.memory.add_message("assistant", decision.reply, {"chat_id": chat_id})
        if bootstrap_context:
            self.store.mark_chat_bootstrapped(chat_id, _utc_now())
        return QueenReply(immediate=_normalize_plain_text(decision.reply), followup=None)

    async def _run_worker(
        self,
        task: str,
        chat_id: int,
        approval_requester,
        permissions: dict[str, bool] | None,
        lifecycle: str | None,
    ) -> WorkerResult:
        worker_id = str(uuid4())
        logger.info("Queen spawning worker: id=%s", worker_id)
        requested_caps = _capabilities_from_permissions(permissions)
        granted = self.policy.grant_capabilities(requested_caps)
        logger.info(
            "Queen worker caps: requested=%s granted=%s",
            len(requested_caps),
            len(granted),
        )
        spec = WorkerSpec(
            id=worker_id,
            task=task,
            system_prompt=_build_worker_prompt(task, granted, task_instructions=""),
            requested_capabilities=requested_caps,
            granted_capabilities=granted,
            timeout_seconds=300,
            memory_limit_mb=256,
            lifecycle=lifecycle or "ephemeral",
            worker_module="broodmind.workers.reference.generic_worker",
        )
        if approval_requester is None:
            approval_requester = lambda intent: self.approvals.request_approval(chat_id, intent)
        result = await self.runtime.run(spec, approval_requester=approval_requester)
        logger.info(
            "Queen worker completed: id=%s evidence=%s intents_exec=%s",
            worker_id,
            len(result.evidence),
            len(result.intents_executed),
        )
        return result

    async def _run_and_compose_reply(
        self,
        task: str,
        chat_id: int,
        approval_requester,
        permissions: dict[str, bool] | None = None,
        lifecycle: str | None = None,
    ) -> str:
        logger.info("Queen awaiting worker result")
        result = await self._run_worker(task, chat_id, approval_requester, permissions, lifecycle)
        logger.info("Queen composing user reply from worker result")
        response = await _compose_user_reply(self.provider, self.memory, task, chat_id, result)
        await self.memory.add_message("assistant", response, {"chat_id": chat_id})
        return response


@dataclass
class QueenReply:
    immediate: str
    followup: "asyncio.Task[str] | None"


def _format_worker_result(result: WorkerResult) -> str:
    summary = _normalize_plain_text(result.summary)
    lines = [f"Worker summary: {summary}"]
    if result.intents_executed:
        lines.append(f"Intents executed: {len(result.intents_executed)}")
    if result.evidence:
        evidence = result.evidence[0]
        snippet = _normalize_plain_text(str(evidence.content))[:200] if evidence.content is not None else ""
        if snippet:
            lines.append(f"Evidence: {snippet}")
    return "\n".join(lines)


QUEEN_SYSTEM_PROMPT = ""


def _build_worker_prompt(
    task: str,
    granted_capabilities: list[Capability],
    task_instructions: str,
) -> str:
    permissions = _format_permissions(granted_capabilities)
    worker_prompt = _load_prompt("worker_system.md")
    template = (
        f"{worker_prompt}\n\n"
        f"{_current_datetime_prompt()}\n\n"
        "Permissions\n"
        f"{permissions}\n\n"
        "Task\n"
        f"{task}\n\n"
        "Task-Specific Instructions\n"
        f"{task_instructions}\n"
    )
    return template


def _format_capabilities(capabilities: list[Capability]) -> str:
    if not capabilities:
        return "none"
    lines = []
    for cap in capabilities:
        lines.append(f"- {cap.type}: {cap.scope} (read_only={cap.read_only})")
    return "\n".join(lines)


def _format_permissions(capabilities: list[Capability]) -> str:
    flags = {
        "network": False,
        "filesystem_read": False,
        "filesystem_write": False,
        "exec": False,
        "email": False,
        "payment": False,
    }
    for cap in capabilities:
        if cap.type == "network":
            flags["network"] = True
        elif cap.type == "filesystem":
            flags["filesystem_read"] = True
            if not cap.read_only:
                flags["filesystem_write"] = True
        elif cap.type == "exec":
            flags["exec"] = True
        elif cap.type == "email":
            flags["email"] = True
        elif cap.type == "payment":
            flags["payment"] = True
    return "\n".join([f"- {key}: {str(value).lower()}" for key, value in flags.items()])


def _normalize_plain_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("* ", "- ")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("#", "")
    cleaned = cleaned.replace("> ", "")
    return cleaned.strip()


def _load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).parent / "prompts" / filename
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _get_queen_system_prompt() -> str:
    global QUEEN_SYSTEM_PROMPT
    if not QUEEN_SYSTEM_PROMPT:
        QUEEN_SYSTEM_PROMPT = _load_prompt("queen_system.md")
    return QUEEN_SYSTEM_PROMPT


def _get_queen_section(title: str) -> str:
    content = _get_queen_system_prompt()
    if not content:
        return ""
    marker = f"## {title}"
    start = content.find(marker)
    if start == -1:
        return ""
    start = start + len(marker)
    end = content.find("\n## ", start)
    section = content[start:end] if end != -1 else content[start:]
    section = section.strip()
    if not section:
        return ""
    return f"{title}:\n{section}"


def _get_persona_prompt() -> str:
    workspace = os.getenv("BROODMIND_WORKSPACE_DIR", "workspace")
    persona_path = Path(workspace) / "PERSONA.MD"
    if not persona_path.exists():
        return ""
    try:
        return persona_path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _get_bootstrap_context(store: Store, chat_id: int) -> str:
    if store.is_chat_bootstrapped(chat_id):
        return ""
    agents_text = _read_workspace_file("AGENTS.md", max_chars=8000)
    if not agents_text:
        return ""
    return "<workspace>\n<file name=\"AGENTS.md\">\n" + agents_text + "\n</file>\n</workspace>"


def _read_workspace_file(filename: str, max_chars: int) -> str:
    workspace = os.getenv("BROODMIND_WORKSPACE_DIR", "workspace")
    target = Path(workspace) / filename
    if not target.exists():
        return ""
    try:
        data = target.read_text(encoding="utf-8")
    except Exception:
        return ""
    if len(data) <= max_chars:
        return data.strip()
    return data[:max_chars].rstrip() + "\n...[truncated]"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _workers_root() -> Path:
    workspace = os.getenv("BROODMIND_WORKSPACE_DIR", "workspace")
    return Path(workspace) / "workers"


def _workers_registry_path() -> Path:
    return _workers_root() / "registry.json"


def _get_workers_registry() -> list[dict]:
    registry_path = _workers_registry_path()
    if not registry_path.exists():
        return []
    try:
        import json

        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _format_workers_registry(entries: list[dict]) -> str:
    if not entries:
        return "No workers registered."
    lines = ["Workers:"]
    for entry in entries:
        wid = entry.get("id", "unknown")
        module = entry.get("module", "unknown")
        task = entry.get("task", "unknown")
        last_used = entry.get("last_used_at", "unknown")
        lifecycle = entry.get("lifecycle", "unknown")
        status = entry.get("status", "unknown")
        lines.append(
            f"- {wid} | {module} | {task} | lifecycle={lifecycle} | status={status} | last_used={last_used}"
        )
    return "\n".join(lines)


def _workers_registry_note() -> str:
    entries = _get_workers_registry()
    if not entries:
        return ""
    summary = ", ".join([e.get("id", "unknown") for e in entries[:5]])
    more = ""
    if len(entries) > 5:
        more = f" (+{len(entries) - 5} more)"
    return (
        "Workers registry available. IDs: "
        f"{summary}{more}. Registry path: {str(_workers_registry_path())}"
    )


def _is_list_workers_command(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in {"/workers", "list workers", "show workers", "workers"}


async def _should_delegate_llm(provider: InferenceProvider, user_text: str) -> bool:
    messages = [
        Message(
            role="system",
            content=(
                "You are a router for BroodMind Queen. Decide if the Queen should delegate "
                "the task to a worker. Reply with exactly one token: DELEGATE or RESPOND."
            ),
        ),
        Message(
            role="system",
            content=(
                "Delegate when the task needs web access, file operations, code execution, "
                "or multi-step processing. Respond directly for simple conversational replies."
            ),
        ),
        Message(role="user", content=user_text),
    ]
    try:
        decision = (await provider.complete(messages)).strip().upper()
        return decision.startswith("DELEGATE")
    except Exception:
        return False


@dataclass
class RouteDecision:
    delegate: bool
    reply: str
    task: str | None = None
    permissions: dict[str, bool] | None = None
    lifecycle: str | None = None


async def _route_or_reply(
    provider: InferenceProvider,
    memory: MemoryService,
    user_text: str,
    chat_id: int,
    bootstrap_context: str,
) -> RouteDecision:
    memory_context = await memory.get_context(user_text)
    recent_history = memory.get_recent_history(chat_id, limit=8)
    if recent_history and recent_history[-1][0] == "user" and recent_history[-1][1] == user_text:
        recent_history = recent_history[:-1]
    messages = [Message(role="system", content=_get_queen_system_prompt())]
    persona = _get_persona_prompt()
    if persona:
        messages.append(Message(role="system", content=f"<persona>\n{persona}\n</persona>"))
    if bootstrap_context:
        messages.append(Message(role="system", content=bootstrap_context))
    messages.append(Message(role="system", content=_current_datetime_prompt()))
    messages.append(Message(role="system", content=_language_instruction(user_text)))
    registry_note = _workers_registry_note()
    if registry_note:
        messages.append(Message(role="system", content=registry_note))
    route_prompt = _get_queen_section("Route Instructions")
    if route_prompt:
        messages.append(Message(role="system", content=route_prompt))
    if memory_context:
        messages.append(
            Message(
                role="system",
                content="<context>\n" + "\n".join(memory_context) + "\n</context>",
            )
        )
    if recent_history:
        for role, content in recent_history:
            if role == "user":
                messages.append(Message(role="user", content=content))
            elif role == "assistant":
                messages.append(Message(role="assistant", content=content))
    messages.append(Message(role="user", content=user_text))
    tool_spec = _spawn_worker_tool_spec()
    queen_tools, ctx = _get_queen_tools()
    tool_capable = getattr(provider, "complete_with_tools", None)
    if callable(tool_capable):
        tools = [tool_spec] + [spec.to_openai_tool() for spec in queen_tools]
        for _ in range(4):
            result = await provider.complete_with_tools(messages, tools=tools, tool_choice="auto")
            content_raw = result.get("content", "")
            tool_calls = result.get("tool_calls") or []
            if tool_calls:
                decision = _route_from_tool_calls(tool_calls)
                if decision:
                    return decision
                for call in tool_calls:
                    tool_result = _handle_queen_tool_call(call, queen_tools, ctx)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "content": tool_result,
                        }
                    )
                continue
            if content_raw:
                logger.debug("Queen route-or-reply output: %s", _truncate_for_log(content_raw))
            content = _normalize_plain_text(content_raw)
            return RouteDecision(delegate=False, reply=content)
        return RouteDecision(delegate=False, reply="")
    response_raw = await provider.complete(messages)
    logger.debug("Queen route-or-reply output: %s", _truncate_for_log(response_raw))
    response = _normalize_plain_text(response_raw)
    return RouteDecision(delegate=False, reply=response)


async def _draft_interim_reply(
    provider: InferenceProvider,
    memory: MemoryService,
    user_text: str,
    chat_id: int,
    bootstrap_context: str,
) -> str:
    memory_context = await memory.get_context(user_text)
    recent_history = memory.get_recent_history(chat_id, limit=6)
    if recent_history and recent_history[-1][0] == "user" and recent_history[-1][1] == user_text:
        recent_history = recent_history[:-1]
    messages = [Message(role="system", content=_get_queen_system_prompt())]
    persona = _get_persona_prompt()
    if persona:
        messages.append(Message(role="system", content=f"<persona>\n{persona}\n</persona>"))
    if bootstrap_context:
        messages.append(Message(role="system", content=bootstrap_context))
    messages.append(Message(role="system", content=_current_datetime_prompt()))
    messages.append(Message(role="system", content=_language_instruction(user_text)))
    registry_note = _workers_registry_note()
    if registry_note:
        messages.append(Message(role="system", content=registry_note))
    interim_prompt = _get_queen_section("Interim Reply Instructions")
    if interim_prompt:
        messages.append(Message(role="system", content=interim_prompt))
    if memory_context:
        messages.append(
            Message(
                role="system",
                content="<context>\n" + "\n".join(memory_context) + "\n</context>",
            )
        )
    if recent_history:
        for role, content in recent_history:
            if role == "user":
                messages.append(Message(role="user", content=content))
            elif role == "assistant":
                messages.append(Message(role="assistant", content=content))
    messages.append(Message(role="user", content=user_text))
    response = await provider.complete(messages)
    logger.debug("Queen interim reply: %s", _truncate_for_log(response))
    cleaned = _normalize_plain_text(response)
    return cleaned


async def _compose_user_reply(
    provider: InferenceProvider,
    memory: MemoryService,
    user_text: str,
    chat_id: int,
    result: WorkerResult,
) -> str:
    import json

    worker_payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    memory_context = await memory.get_context(user_text)
    recent_history = memory.get_recent_history(chat_id, limit=8)
    if recent_history and recent_history[-1][0] == "user" and recent_history[-1][1] == user_text:
        recent_history = recent_history[:-1]
    messages = [
        Message(role="system", content=_get_queen_system_prompt()),
        Message(role="system", content=_current_datetime_prompt()),
        Message(role="system", content=_language_instruction(user_text)),
        Message(role="system", content=_get_queen_section("Followup Reply Instructions")),
    ]
    persona = _get_persona_prompt()
    if persona:
        messages.insert(1, Message(role="system", content=f"<persona>\n{persona}\n</persona>"))
    registry_note = _workers_registry_note()
    if registry_note:
        messages.append(Message(role="system", content=registry_note))
    if memory_context:
        messages.append(
            Message(
                role="system",
                content="<context>\n" + "\n".join(memory_context) + "\n</context>",
            )
        )
    if recent_history:
        for role, content in recent_history:
            if role == "user":
                messages.append(Message(role="user", content=content))
            elif role == "assistant":
                messages.append(Message(role="assistant", content=content))
    messages.append(Message(role="system", content=f"<worker_result>\n{worker_payload}\n</worker_result>"))
    messages.append(Message(role="user", content=user_text))
    response = await provider.complete(messages)
    logger.debug("Queen followup reply: %s", _truncate_for_log(response))
    return _normalize_plain_text(response)


def _language_instruction(text: str) -> str:
    if _contains_cyrillic(text):
        return (
            "Respond in Russian. Use plain text only (no markdown, no tables). "
            "Do not switch languages mid-conversation."
        )
    return (
        "Respond in English. Use plain text only (no markdown, no tables). "
        "Do not switch languages mid-conversation."
    )


def _contains_cyrillic(text: str) -> bool:
    return any("а" <= ch.lower() <= "я" for ch in text)


def _current_datetime_prompt() -> str:
    now = datetime.now().astimezone()
    return f"Current date/time: {now.isoformat()}"


def _truncate_for_log(text: str, limit: int = 1200) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _spawn_worker_tool_spec() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "spawn_worker",
            "description": "Spawn a worker with task and permissions. Returns worker_id and updates workspace/workers/registry.json.",
            "parameters": {
                "type": "object",
                "properties": {
                    "interim_reply": {"type": "string"},
                    "task": {"type": "string"},
                    "permissions": {
                        "type": "object",
                        "properties": {
                            "network": {"type": "boolean"},
                            "filesystem_read": {"type": "boolean"},
                            "filesystem_write": {"type": "boolean"},
                            "exec": {"type": "boolean"},
                            "email": {"type": "boolean"},
                            "payment": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                    "lifecycle": {"type": "string", "enum": ["ephemeral", "reusable"]},
                },
                "required": ["interim_reply", "task", "permissions", "lifecycle"],
                "additionalProperties": False,
            },
        },
    }


def _route_from_tool_calls(tool_calls: list[dict]) -> RouteDecision | None:
    if not tool_calls:
        return None
    call = tool_calls[0]
    function = call.get("function") if isinstance(call, dict) else None
    if not function or function.get("name") != "spawn_worker":
        return None
    args_raw = function.get("arguments")
    if not isinstance(args_raw, str):
        return None
    try:
        import json

        args = json.loads(args_raw)
    except Exception:
        return None
    if not isinstance(args, dict):
        return None
    logger.debug("Queen tool call spawn_worker args: %s", _truncate_for_log(str(args)))
    return RouteDecision(
        delegate=True,
        reply=str(args.get("interim_reply") or ""),
        task=str(args.get("task") or ""),
        permissions=args.get("permissions") if isinstance(args.get("permissions"), dict) else None,
        lifecycle=str(args.get("lifecycle") or ""),
    )


def _get_queen_tools() -> tuple[list[ToolSpec], dict[str, object]]:
    perms = {"filesystem_read": True, "filesystem_write": True}
    ctx = {"base_dir": Path(os.getenv("BROODMIND_WORKSPACE_DIR", "workspace")).resolve()}
    tool_specs = filter_tools(get_tools(), scope="queen", permissions=perms)
    return tool_specs, ctx


def _handle_queen_tool_call(
    call: dict,
    tools: list[ToolSpec],
    ctx: dict[str, object],
) -> str:
    function = call.get("function") or {}
    name = function.get("name")
    args_raw = function.get("arguments", "{}")
    try:
        import json

        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    except Exception:
        args = {}
    logger.debug("Queen tool call: %s", name)
    for spec in tools:
        if spec.name == name:
            return spec.handler(args, ctx)
    return "Unknown tool."


def _capabilities_from_permissions(permissions: dict[str, bool] | None) -> list[Capability]:
    if not permissions:
        return [Capability(type="network", scope="*", read_only=True)]
    caps: list[Capability] = []
    if permissions.get("network"):
        caps.append(Capability(type="network", scope="*", read_only=True))
    if permissions.get("filesystem_read") or permissions.get("filesystem_write"):
        caps.append(
            Capability(
                type="filesystem",
                scope="/workspace/**",
                read_only=not bool(permissions.get("filesystem_write")),
            )
        )
    if permissions.get("exec"):
        caps.append(Capability(type="exec", scope="*", read_only=False))
    if permissions.get("email"):
        caps.append(Capability(type="email", scope="*", read_only=False))
    if permissions.get("payment"):
        caps.append(Capability(type="payment", scope="*", read_only=False))
    return caps
