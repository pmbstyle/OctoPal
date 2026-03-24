"""OpenRouter-based inference provider."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

import httpx

from octopal.infrastructure.config.settings import Settings
from octopal.infrastructure.providers.base import Message

logger = logging.getLogger(__name__)

_LOG_MAX_CHARS = 400


class OpenRouterProvider:
    """OpenRouter-based inference provider."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.openrouter_api_key
        self._base_url = settings.openrouter_base_url.rstrip("/")
        self._model = settings.openrouter_model
        self._timeout = settings.openrouter_timeout

    async def complete(self, messages: list[Message | dict], **kwargs: object) -> str:
        """Complete a chat request without tools."""
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        serialized_messages = [_serialize_message(m) for m in messages]
        payload_str = json.dumps({"messages": serialized_messages}, ensure_ascii=False)

        logger.debug(
            "OpenRouter request: model=%s, messages=%d, total_chars=%d",
            self._model,
            len(serialized_messages),
            len(payload_str),
        )

        if self._settings.debug_prompts:
            logger.debug("OpenRouter payload: %s", _truncate(payload_str))

        payload = {
            "model": self._model,
            "messages": serialized_messages,
            "temperature": float(kwargs.get("temperature", 0.3)),
        }

        timeout = httpx.Timeout(self._timeout, connect=30.0)
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
                response = await client.post(
                    "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            content = _extract_content(data)
            logger.debug("OpenRouter response: %s", _truncate(content))
            return content
        except httpx.HTTPStatusError as exc:
            logger.exception("OpenRouter HTTP error: %s", exc.response.status_code)
            raise RuntimeError(f"OpenRouter request failed: {exc}") from exc
        except Exception as exc:
            logger.exception("OpenRouter completion failed")
            raise RuntimeError(f"OpenRouter completion failed: {exc}") from exc

    async def complete_stream(
        self,
        messages: list[Message | dict],
        *,
        on_partial: Callable[[str], Awaitable[None]],
        **kwargs: object,
    ) -> str:
        """Streaming fallback for providers without incremental transport in this adapter."""
        text = await self.complete(messages, **kwargs)
        if text:
            try:
                await on_partial(text)
            except Exception:
                logger.debug("OpenRouter partial callback failed", exc_info=True)
        return text

    async def complete_with_tools(
        self,
        messages: list[Message | dict],
        *,
        tools: list[dict],
        tool_choice: str = "auto",
        **kwargs: object,
    ) -> dict:
        """Complete a chat request with tool/function calling."""
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        serialized_messages = [_serialize_message(m) for m in messages]
        payload_str = json.dumps(
            {"messages": serialized_messages, "tools": tools, "tool_choice": tool_choice},
            ensure_ascii=False,
        )
        tool_names = [t.get("function", {}).get("name") for t in tools]

        logger.debug(
            "OpenRouter request (tools): model=%s, messages=%d, tools=%s, total_chars=%d",
            self._model,
            len(serialized_messages),
            tool_names,
            len(payload_str),
        )

        if self._settings.debug_prompts:
            logger.debug("OpenRouter payload (tools): %s", _truncate(payload_str))

        payload = {
            "model": self._model,
            "messages": serialized_messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": float(kwargs.get("temperature", 0.3)),
        }

        timeout = httpx.Timeout(self._timeout, connect=30.0)
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
                response = await client.post(
                    "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            content = _extract_content(data)
            tool_calls = _extract_tool_calls(data)

            if content:
                logger.debug("OpenRouter response (tools) content: %s", _truncate(content))
            if tool_calls:
                tool_call_names = [tc.get("function", {}).get("name") for tc in tool_calls]
                logger.debug("OpenRouter response: tool_calls=%s", tool_call_names)
                if self._settings.debug_prompts:
                    logger.debug(
                        "OpenRouter tool_calls payload: %s",
                        _truncate(json.dumps(tool_calls, ensure_ascii=False)),
                    )

            return {"content": content, "tool_calls": tool_calls}
        except httpx.HTTPStatusError as exc:
            logger.exception("OpenRouter HTTP error: %s", exc.response.status_code)
            raise RuntimeError(f"OpenRouter request failed: {exc}") from exc
        except Exception as exc:
            logger.exception("OpenRouter completion with tools failed")
            raise RuntimeError(f"OpenRouter completion with tools failed: {exc}") from exc


def _serialize_message(message: Message | dict) -> dict:
    """Serialize a message to dict format."""
    if isinstance(message, dict):
        return message
    return message.to_dict()


def _extract_content(response: dict) -> str:
    """Extract content from OpenRouter response."""
    try:
        return response.get("choices", [{}])[0].get("message", {}).get("content") or ""
    except Exception as exc:
        logger.warning("Failed to extract content from response: %s", exc)
        return ""


def _extract_tool_calls(response: dict) -> list[dict]:
    """Extract tool calls from OpenRouter response."""
    try:
        message = response.get("choices", [{}])[0].get("message", {})
        raw_tool_calls = message.get("tool_calls")
        if raw_tool_calls:
            if isinstance(raw_tool_calls, list):
                return raw_tool_calls
            elif isinstance(raw_tool_calls, dict):
                return [raw_tool_calls]
        return []
    except Exception as exc:
        logger.warning("Failed to extract tool calls from response: %s", exc)
        return []


def _truncate(text: str) -> str:
    """Truncate text for logging."""
    if text is None:
        return ""
    if len(text) <= _LOG_MAX_CHARS:
        return text
    return text[:_LOG_MAX_CHARS] + f"...[truncated {len(text)} bytes]"
