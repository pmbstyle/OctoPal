from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import structlog

from broodmind.providers.base import InferenceProvider, Message
from broodmind.memory.service import MemoryService
from broodmind.memory.canon import CanonService
from broodmind.queen.prompt_builder import build_queen_prompt, build_bootstrap_context_prompt
from broodmind.tools.registry import ToolSpec, filter_tools
from broodmind.tools.tools import get_tools
from broodmind.utils import is_heartbeat_ok, is_control_response
from broodmind.workers.contracts import WorkerResult

logger = structlog.get_logger(__name__)


async def route_or_reply(
    queen: Any,
    provider: InferenceProvider,
    memory: MemoryService,
    user_text: str,
    chat_id: int,
    bootstrap_context: str,
    *,
    internal_followup: bool = False,
    show_typing: bool = True,
    images: list[str] | None = None,
) -> str:
    """Core routing logic: decide whether to use tools or reply to user."""
    # Internal chat_id (<= 0) should not trigger typing indicators.
    if chat_id > 0 and show_typing:
        await queen.set_typing(chat_id, True)
    
    await queen.set_thinking(True)
    try:
        is_ws = getattr(queen, "is_ws_active", False)
        messages = await build_queen_prompt(
            store=queen.store, 
            memory=memory, 
            canon=queen.canon, 
            user_text=user_text, 
            chat_id=chat_id, 
            bootstrap_context=bootstrap_context,
            is_ws=is_ws,
            images=images
        )
        _log_system_prompt(messages, "route")
        
        queen_tools, ctx = _get_queen_tools(queen, chat_id)
        logger.info("Queen tools fetched: count=%d", len(queen_tools))
        tool_capable = getattr(provider, "complete_with_tools", None)
        
        if callable(tool_capable):
            tools = [spec.to_openai_tool() for spec in queen_tools]
            last_error: str | None = None
            had_tool_calls = False
            max_attempts = 10
            
import base64
import uuid
# ... (rest of imports)

async def route_or_reply(
    # ... args ...
) -> str:
    # ... (start of function) ...
    
        if callable(tool_capable):
            tools = [spec.to_openai_tool() for spec in queen_tools]
            last_error: str | None = None
            had_tool_calls = False
            max_attempts = 10
            
            for _ in range(max_attempts):
                try:
                    result = await provider.complete_with_tools(messages, tools=tools, tool_choice="auto")
                except Exception as e:
                    # If we have images, this might be a multi-modal conflict (e.g. z.ai GLM-4 doesn't support tools + vision).
                    # Fallback strategy: Save images to disk and retry with a text-only prompt pointing to the files.
                    if images:
                        logger.warning("Vision+Tools failed; attempting save-to-disk fallback", error=str(e))
                        try:
                            # 1. Save images to disk
                            saved_paths = []
                            workspace_dir = Path(os.getenv("BROODMIND_WORKSPACE_DIR", "workspace")).resolve()
                            img_dir = workspace_dir / "tmp" / "telegram_images"
                            img_dir.mkdir(parents=True, exist_ok=True)
                            
                            for idx, img_data in enumerate(images):
                                # expect data:image/jpeg;base64,....
                                if "," in img_data:
                                    header, b64_str = img_data.split(",", 1)
                                    ext = ".jpg"
                                    if "png" in header: ext = ".png"
                                    elif "webp" in header: ext = ".webp"
                                else:
                                    b64_str = img_data
                                    ext = ".jpg" # assume jpg
                                
                                file_name = f"img_{uuid.uuid4()}{ext}"
                                file_path = img_dir / file_name
                                with open(file_path, "wb") as f:
                                    f.write(base64.b64decode(b64_str))
                                saved_paths.append(str(file_path))
                            
                            # 2. Construct new text-only message
                            fallback_text = (
                                f"{user_text}\n\n"
                                "[SYSTEM NOTE: User sent {len(images)} image(s). Direct vision processing failed (provider rejected multimodal payload). "
                                "The images have been saved locally at:\n" + 
                                "\n".join([f"- {p}" for p in saved_paths]) + 
                                "\nIf you have file analysis tools, you can use them on these paths. Otherwise, ask the user for a description.]"
                            )
                            
                            # 3. Replace the last message (which had the image payload) with text-only version
                            # effectively 'popping' the failed multimodal message and replacing it
                            logger.info("Retrying with text-only fallback and saved images", count=len(saved_paths))
                            messages[-1] = {"role": "user", "content": fallback_text}
                            
                            # 4. Disable images flag so we don't loop forever if this retry fails too
                            images = None 
                            continue 
                            
                        except Exception as fallback_exc:
                            logger.error("Fallback save-and-retry failed", error=str(fallback_exc))
                            return "I see you sent an image, but I am unable to process it. My current model configuration might not support vision, and I could not save it for tool analysis."
                    raise e
                
                content_raw = result.get("content", "")
                # ... (rest of loop)
                tool_calls = result.get("tool_calls") or []
                
                if tool_calls:
                    had_tool_calls = True
                    assistant_msg: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
                    if content_raw:
                        assistant_msg["content"] = content_raw
                    messages.append(assistant_msg)
                    
                    for call in tool_calls:
                        tool_result = await _handle_queen_tool_call(call, queen_tools, ctx)
                        tool_result_text = (
                            tool_result
                            if isinstance(tool_result, str)
                            else json.dumps(tool_result, ensure_ascii=False)
                        )
                        messages.append(
                            {"role": "tool", "tool_call_id": call.get("id"), "content": tool_result_text}
                        )
                        if "error" in tool_result_text.lower() or "failed" in tool_result_text.lower():
                            last_error = tool_result_text
                    continue
                
                if content_raw:
                    logger.debug("Queen output", output=content_raw)
                return normalize_plain_text(content_raw)
                
            if had_tool_calls:
                if internal_followup:
                    return "NO_USER_RESPONSE"
                # Force a final response without tools to explain progress.
                messages.append(
                    Message(
                        role="system",
                        content="You have reached the tool call limit for this turn. Summarize what you have initiated and let the user know you are processing their request.",
                    )
                )
                final_resp = await provider.complete(messages)
                return normalize_plain_text(final_resp)
                
            if last_error and _looks_like_tool_error(last_error):
                if internal_followup:
                    return "NO_USER_RESPONSE"
                messages.append(
                    Message(
                        role="system",
                        content=f"A tool call failed: {last_error}. Explain the problem to the user naturally and ask for guidance if needed.",
                    )
                )
                final_resp = await provider.complete(messages)
                return normalize_plain_text(final_resp)
                
            return ""
            
        response_raw = await provider.complete(messages)
        logger.debug("Queen output", output=response_raw)
        return normalize_plain_text(response_raw)
    except Exception:
        logger.exception("Error in route_or_reply")
        raise
    finally:
        await queen.set_thinking(False)
        if chat_id > 0 and show_typing:
            logger.debug("Toggling typing indicator off", chat_id=chat_id)
            await queen.set_typing(chat_id, False)


async def route_worker_result_back_to_queen(
    queen: Any,
    chat_id: int,
    task_text: str,
    result: WorkerResult,
) -> str:
    """Decide next steps after a worker completes its task."""
    output_summary = result.output
    output_truncated = False
    available_keys = []

    if isinstance(result.output, dict):
        available_keys = list(result.output.keys())
        if len(json.dumps(result.output)) > 8000:
            output_summary = {k: f"<{type(v).__name__}>" for k, v in result.output.items()}
            output_truncated = True

    payload = {
        "task": task_text,
        "summary": result.summary,
        "output": output_summary,
        "output_truncated": output_truncated,
        "available_keys": available_keys,
        "questions": result.questions,
        "knowledge_proposals": [p.model_dump() for p in result.knowledge_proposals],
        "tools_used": result.tools_used,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    worker_result_prompt = (
        "Worker completed. Decide and execute next action based on this payload.\n"
        "<worker_result>\n"
        f"{payload_json}\n"
        "</worker_result>\n\n"
        "If the output is truncated and you need specific details, use `get_worker_output_path`.\n"
        "If there are knowledge_proposals, review them and use `manage_canon` to save them if valid.\n"
        "If a user-facing response is required now, provide it in plain text.\n"
        "If no user-facing response is needed, return exactly: NO_USER_RESPONSE"
    )
    
    bootstrap_context = await build_bootstrap_context_prompt(queen.store, chat_id)
    reply_text = await route_or_reply(
        queen,
        queen.provider,
        queen.memory,
        worker_result_prompt,
        chat_id,
        bootstrap_context.content,
        internal_followup=True,
    )
    return normalize_plain_text(reply_text)


def should_send_worker_followup(text: str) -> bool:
    """Determine if a worker follow-up should be sent to the user."""
    if is_control_response(text):
        return False
    return True


def normalize_plain_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.strip()


def _looks_like_tool_error(text: str) -> bool:
    lowered = text.lower()
    return " error" in lowered or "failed" in lowered


def _log_system_prompt(messages: list[Message], label: str) -> None:
    system_lengths = [len(m.content) for m in messages if m.role == "system" and m.content]
    if system_lengths:
        logger.debug(
            "Queen system prompt",
            label=label,
            parts=len(system_lengths),
            total_chars=sum(system_lengths),
        )


def _get_queen_tools(queen: Any, chat_id: int) -> tuple[list[ToolSpec], dict[str, object]]:
    perms = {
        "filesystem_read": True,
        "filesystem_write": True,
        "worker_manage": True,
        "llm_subtask": True,
        "canon_manage": True,
        "network": True,
        "exec": True,
        "service_read": True,
        "service_control": True,
        "deploy_control": True,
        "db_admin": True,
        "security_audit": True,
        "self_control": True,
        "mcp_exec": True,
    }
    ctx = {
        "base_dir": Path(os.getenv("BROODMIND_WORKSPACE_DIR", "workspace")).resolve(),
        "queen": queen,
        "chat_id": chat_id
    }
    mcp_manager = getattr(queen, "mcp_manager", None)
    tool_specs = filter_tools(get_tools(mcp_manager=mcp_manager), permissions=perms)
    # Remove web_fetch from Queen; only workers are allowed to fetch raw web content.
    tool_specs = [spec for spec in tool_specs if spec.name != "web_fetch"]
    return tool_specs, ctx


async def _handle_queen_tool_call(call: dict, tools: list[ToolSpec], ctx: dict[str, object]) -> str:
    function = call.get("function") or {}
    name = function.get("name")
    args_raw = function.get("arguments", "{}")
    try:
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
    except Exception:
        args = {}
    
    logger.debug("Queen tool call", tool_name=name, args=args)
    for spec in tools:
        if spec.name == name:
            if spec.is_async:
                import inspect
                result = spec.handler(args, ctx)
                if inspect.isawaitable(result):
                    result = await result
            else:
                result = await asyncio.to_thread(spec.handler, args, ctx)
            logger.debug("Queen tool result", tool_name=name, result_preview=f"{str(result)[:200]}...")
            return result
    return f"Unknown tool: {name}"
