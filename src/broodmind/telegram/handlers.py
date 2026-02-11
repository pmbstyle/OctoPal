from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from broodmind.config.settings import Settings
from broodmind.logging_config import correlation_id_var
from broodmind.queen.core import Queen, QueenReply
from broodmind.runtime_metrics import update_component_gauges
from broodmind.state import update_last_message
from broodmind.telegram.approvals import ApprovalManager

logger = logging.getLogger(__name__)
_CHAT_LOCKS: dict[int, asyncio.Lock] = {}
_CHAT_QUEUES: dict[int, asyncio.Queue[str]] = {}
_CHAT_SEND_TASKS: dict[int, asyncio.Task] = {}
_SEND_IDLE_TIMEOUT_SECONDS = 300.0
_TELEGRAM_PARSE_MODE: str | None = None
_MDV2_SPECIAL_CHARS = set("_*[]()~`>#+-=|{}.!\\")


def _publish_runtime_metrics() -> None:
    update_component_gauges(
        "telegram",
        {
            "chat_locks": len(_CHAT_LOCKS),
            "chat_queues": len(_CHAT_QUEUES),
            "send_tasks": len(_CHAT_SEND_TASKS),
        },
    )


def register_handlers(
    dp: Dispatcher, queen: Queen, approvals: ApprovalManager, settings: Settings, bot: Bot
) -> None:
    global _TELEGRAM_PARSE_MODE
    _TELEGRAM_PARSE_MODE = _normalize_parse_mode(settings.telegram_parse_mode)

    async def _internal_send(chat_id: int, text: str) -> None:
        await _enqueue_send(bot, chat_id, text)
    async def _internal_progress_send(
        chat_id: int,
        state: str,
        text: str,
        meta: dict[str, object],
    ) -> None:
        # Progress events are for internal tracking/logging only.
        # User-facing updates are handled by the Queen after worker completion or via her immediate replies.
        logger.info("Worker progress event", chat_id=chat_id, state=state, text=text)

    queen.internal_send = _internal_send
    queen.internal_progress_send = _internal_progress_send

    @dp.message()
    async def handle_message(message: Message) -> None:
        # Generate a unique ID for this request chain
        correlation_id = f"msg-{uuid.uuid4()}"
        correlation_id_var.set(correlation_id)

        if not message.text:
            return
        logger.debug("Incoming message from chat_id=%s", message.chat.id)
        lock = _CHAT_LOCKS.setdefault(message.chat.id, asyncio.Lock())
        _publish_runtime_metrics()
        async with lock:
            typing_stop = asyncio.Event()
            typing_task = asyncio.create_task(_typing_loop(message, typing_stop))
            try:
                reply = await queen.handle_message(message.text, message.chat.id)
            except Exception:
                logger.exception("Failed to handle message")
                # Avoid leaking technical error details to the user.
                # The Queen's internal failure logs will capture the detail.
                typing_stop.set()
                return
            finally:
                typing_stop.set()
                if not typing_task.done():
                    typing_task.cancel()

            if isinstance(reply, QueenReply):
                update_last_message(settings)
                if reply.immediate:
                    await _enqueue_send(message.bot, message.chat.id, reply.immediate)
                return

        update_last_message(settings)
        await _enqueue_send(message.bot, message.chat.id, str(reply))

    @dp.callback_query()
    async def handle_callback(query: CallbackQuery) -> None:
        data = query.data or ""
        if data.startswith("approve:"):
            intent_id = data.split(":", 1)[1]
            approvals.resolve(intent_id, True)
            await query.answer("Intent Approved")
            if query.message:
                await query.message.edit_reply_markup(reply_markup=None)
            return
        if data.startswith("deny:"):
            intent_id = data.split(":", 1)[1]
            approvals.resolve(intent_id, False)
            await query.answer("Intent Denied")
            if query.message:
                await query.message.edit_reply_markup(reply_markup=None)


async def _send_chunked(bot: Bot, chat_id: int, text: str, limit: int = 4000) -> None:
    chunks = _chunk_text(text, limit)
    for chunk in chunks:
        await _send_message_safe(bot, chat_id, chunk)


async def _send_message_safe(bot: Bot, chat_id: int, text: str) -> None:
    parse_mode = _TELEGRAM_PARSE_MODE
    outbound = text
    if parse_mode == "MarkdownV2":
        outbound = _prepare_markdown_v2(text)
    if not parse_mode:
        await bot.send_message(chat_id, text)
        return
    try:
        await bot.send_message(chat_id, outbound, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        # Formatting mismatch should not drop the message for the user.
        logger.warning(
            "Telegram parse failed; retrying without parse_mode (parse_mode=%s, error=%s)",
            parse_mode,
            exc,
        )
        await bot.send_message(chat_id, text)


async def _enqueue_send(bot: Bot, chat_id: int, text: str) -> None:
    queue = _CHAT_QUEUES.get(chat_id)
    if not queue:
        queue = asyncio.Queue()
        _CHAT_QUEUES[chat_id] = queue

    # If the task is missing or has finished, create a new one.
    if chat_id not in _CHAT_SEND_TASKS or _CHAT_SEND_TASKS[chat_id].done():
        _CHAT_SEND_TASKS[chat_id] = asyncio.create_task(_sender_loop(bot, chat_id, queue))
    _publish_runtime_metrics()

    await queue.put(text)


async def _sender_loop(bot: Bot, chat_id: int, queue: asyncio.Queue[str]) -> None:
    while True:
        try:
            # Wait for a new message, but with a timeout.
            text = await asyncio.wait_for(queue.get(), timeout=_SEND_IDLE_TIMEOUT_SECONDS)
        except TimeoutError:
            # Queue has been empty for the timeout duration, so this worker can exit.
            break

        try:
            await _send_chunked(bot, chat_id, text)
        except Exception:
            logger.exception("Failed to send queued message")
        finally:
            queue.task_done()

    # The task is now finished, remove it from the registry so a new one can be created later.
    _CHAT_SEND_TASKS.pop(chat_id, None)
    # Drop idle queue to avoid unbounded per-chat growth over long runtimes.
    if queue.empty():
        _CHAT_QUEUES.pop(chat_id, None)
    _publish_runtime_metrics()
    logger.debug("Sender loop for chat_id=%s finished due to inactivity.", chat_id)


async def _typing_loop(message: Message, stop: asyncio.Event) -> None:
    try:
        while not stop.is_set():
            await message.bot.send_chat_action(message.chat.id, action="typing")
            try:
                await asyncio.wait_for(stop.wait(), timeout=4.0)
            except TimeoutError:
                continue
    except Exception:
        logger.debug("Typing indicator failed", exc_info=True)


def _chunk_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    return [p for p in parts if p]


def _normalize_parse_mode(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered == "markdownv2":
        return "MarkdownV2"
    if lowered == "html":
        return "HTML"
    if lowered in {"markdown", "markdownv1"}:
        return "Markdown"
    logger.warning("Unknown BROODMIND_TELEGRAM_PARSE_MODE value; using plain text (value=%s)", value)
    return None


def _prepare_markdown_v2(text: str) -> str:
    """Best-effort MarkdownV2 sanitizer that preserves common markdown entities."""
    source = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    protected: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        token = f"\u0000BMMD{len(protected)}\u0000"
        value = match.group(0)
        if value.startswith("**") and value.endswith("**") and len(value) >= 4:
            # Convert common markdown bold to Telegram MarkdownV2 bold.
            value = f"*{value[2:-2]}*"
        protected.append(value)
        return token

    patterns = [
        r"```[\s\S]*?```",             # fenced code blocks
        r"`[^`\n]+`",                  # inline code
        r"\[[^\]\n]+\]\([^)]+\)",      # links
        r"\|\|[^|\n]+\|\|",            # spoilers
        r"__[^_\n]+__",                # underline
        r"\*\*[^*\n]+\*\*",            # markdown bold (**...**)
        r"\*[^*\n]+\*",                # bold (*...*)
        r"_[^_\n]+_",                  # italic
        r"~[^~\n]+~",                  # strikethrough
    ]
    for pattern in patterns:
        source = re.sub(pattern, _stash, source)

    escaped = _escape_markdown_v2_plain(source)
    for idx, fragment in enumerate(protected):
        escaped = escaped.replace(f"\u0000BMMD{idx}\u0000", fragment)
    return escaped


def _escape_markdown_v2_plain(text: str) -> str:
    parts: list[str] = []
    for ch in text:
        if ch in _MDV2_SPECIAL_CHARS:
            parts.append(f"\\{ch}")
        else:
            parts.append(ch)
    return "".join(parts)

