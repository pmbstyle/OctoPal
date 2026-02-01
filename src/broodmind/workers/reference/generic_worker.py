from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

from broodmind.worker_sdk.worker import Worker
from broodmind.workers.contracts import WorkerResult
from broodmind.tools.registry import filter_tools, ToolSpec
from broodmind.tools.tools import get_tools


_DEFAULT_ZAI_BASE = "https://api.z.ai/api/coding/paas/v4"
_DEFAULT_ZAI_CHAT_PATH = "/chat/completions"
_LOG_MAX_CHARS = 2000
_MAX_TOOL_ITERS = 4
logger = logging.getLogger(__name__)


async def run_worker(spec_path: str) -> None:
    worker = Worker.from_spec_file(spec_path)
    task = worker.spec.task.strip()
    base_dir = Path(spec_path).parent
    await worker.log("info", f"Worker start: id={worker.spec.id}")

    if not task:
        await worker.complete(
            WorkerResult(
                summary="No task provided.",
                evidence=[],
            )
        )
        return

    response = await _run_llm_with_tools(worker, task, base_dir)
    logger.debug("Worker LLM response: %s", _truncate(response))
    await worker.complete(
        WorkerResult(
            summary=response,
            evidence=[],
        )
    )


async def _run_llm_with_tools(worker: Worker, task: str, base_dir: Path) -> str:
    api_key = os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY")
    if not api_key:
        return "LLM unavailable: missing ZAI_API_KEY."

    tool_specs, ctx = _build_tools(worker, base_dir)
    messages: list[dict] = [
        {"role": "system", "content": worker.spec.system_prompt},
        {"role": "user", "content": task},
    ]
    for _ in range(_MAX_TOOL_ITERS):
        result = await _call_llm(messages, [spec.to_openai_tool() for spec in tool_specs])
        content = (result.get("content") or "").strip()
        tool_calls = result.get("tool_calls") or []
        if tool_calls:
            await worker.log("info", f"Tool calls requested: {len(tool_calls)}")
            for call in tool_calls:
                tool_result = await _handle_tool_call(worker, call, tool_specs, ctx)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": tool_result,
                    }
                )
            continue
        if content:
            return _sanitize_text(content)
        return "Worker completed with no content."

    return "Worker tool loop exceeded iteration limit."


async def _call_llm(messages: list[dict], tools: list[dict]) -> dict:
    base_url = os.getenv("ZAI_BASE_URL", _DEFAULT_ZAI_BASE).rstrip("/")
    chat_path = os.getenv("ZAI_CHAT_PATH", _DEFAULT_ZAI_CHAT_PATH)
    model = os.getenv("ZAI_MODEL", "glm-4.7")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
        "tools": tools,
        "tool_choice": "auto",
    }
    timeout = httpx.Timeout(
        float(os.getenv("ZAI_TIMEOUT_SECONDS", "45")),
        connect=float(os.getenv("ZAI_CONNECT_TIMEOUT_SECONDS", "15")),
    )
    url = f"{base_url}{chat_path}"
    headers = {
        "Authorization": f"Bearer {os.getenv('ZAI_API_KEY') or os.getenv('Z_AI_API_KEY')}",
        "Accept-Language": os.getenv("ZAI_ACCEPT_LANGUAGE", "en-US,en"),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    try:
        message = data["choices"][0]["message"]
        return {
            "content": message.get("content") or "",
            "tool_calls": message.get("tool_calls") or [],
        }
    except Exception:
        return {"content": "LLM returned an invalid response.", "tool_calls": []}


def _build_tools(worker: Worker, base_dir: Path) -> tuple[list[ToolSpec], dict[str, object]]:
    perms = _permissions_from_caps(worker.spec.granted_capabilities)
    ctx = {"base_dir": base_dir}
    tool_specs = filter_tools(get_tools(), scope="worker", permissions=perms)
    return tool_specs, ctx


def _permissions_from_caps(caps: list) -> dict[str, bool]:
    perms = {
        "network": False,
        "filesystem_read": False,
        "filesystem_write": False,
        "exec": False,
    }
    for cap in caps:
        if cap.type == "network":
            perms["network"] = True
        elif cap.type == "filesystem":
            perms["filesystem_read"] = True
            if not cap.read_only:
                perms["filesystem_write"] = True
        elif cap.type == "exec":
            perms["exec"] = True
    return perms


async def _handle_tool_call(
    worker: Worker,
    call: dict,
    tools: list[ToolSpec],
    ctx: dict[str, object],
) -> str:
    function = call.get("function") or {}
    name = function.get("name")
    args_raw = function.get("arguments", "{}")
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    except Exception:
        args = {}
    await worker.log("info", f"Tool call: {name}")
    for spec in tools:
        if spec.name == name:
            return spec.handler(args, ctx)
    return "Unknown tool."


def _sanitize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("* ", "- ")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("`", "")
    cleaned = cleaned.replace("#", "")
    cleaned = cleaned.replace("> ", "")
    return cleaned.strip()


def _truncate(text: str) -> str:
    if text is None:
        return ""
    if len(text) <= _LOG_MAX_CHARS:
        return text
    return text[:_LOG_MAX_CHARS] + "...[truncated]"
