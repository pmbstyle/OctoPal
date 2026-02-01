from __future__ import annotations

import logging

import httpx

from broodmind.config.settings import Settings
from broodmind.providers.base import Message

_LOG_MAX_CHARS = 2000

logger = logging.getLogger(__name__)


class ZAIProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def complete(self, messages: list[Message | dict], **kwargs: object) -> str:
        if not self._settings.zai_api_key:
            raise RuntimeError("ZAI_API_KEY is not set")

        payload = {
            "model": self._settings.zai_model,
            "messages": [_serialize_message(m) for m in messages],
            "temperature": kwargs.get("temperature", 0.3),
            "stream": False,
        }
        logger.debug(
            "ZAI request: model=%s messages=%s",
            self._settings.zai_model,
            len(payload["messages"]),
        )

        timeout = httpx.Timeout(
            self._settings.zai_timeout_seconds,
            connect=self._settings.zai_connect_timeout_seconds,
        )
        url = self._settings.zai_base_url.rstrip("/") + self._settings.zai_chat_path
        headers = {
            "Authorization": f"Bearer {self._settings.zai_api_key}",
            "Accept-Language": self._settings.zai_accept_language,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
            logger.debug("ZAI response: %s", _truncate(content))
            return content
        except (KeyError, IndexError, TypeError) as exc:
            logger.exception("Unexpected ZAI response shape: %s", data)
            raise RuntimeError("Unexpected ZAI response format") from exc

    async def complete_with_tools(
        self,
        messages: list[Message | dict],
        *,
        tools: list[dict],
        tool_choice: str = "auto",
        **kwargs: object,
    ) -> dict:
        if not self._settings.zai_api_key:
            raise RuntimeError("ZAI_API_KEY is not set")

        payload = {
            "model": self._settings.zai_model,
            "messages": [_serialize_message(m) for m in messages],
            "temperature": kwargs.get("temperature", 0.3),
            "stream": False,
            "tools": tools,
            "tool_choice": tool_choice,
        }
        logger.debug(
            "ZAI request (tools): model=%s messages=%s tools=%s",
            self._settings.zai_model,
            len(payload["messages"]),
            len(tools),
        )

        timeout = httpx.Timeout(
            self._settings.zai_timeout_seconds,
            connect=self._settings.zai_connect_timeout_seconds,
        )
        url = self._settings.zai_base_url.rstrip("/") + self._settings.zai_chat_path
        headers = {
            "Authorization": f"Bearer {self._settings.zai_api_key}",
            "Accept-Language": self._settings.zai_accept_language,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
            if content:
                logger.debug("ZAI response (tools) content: %s", _truncate(content))
            if tool_calls:
                logger.debug("ZAI response (tools) tool_calls=%s", len(tool_calls))
            return {"content": content, "tool_calls": tool_calls}
        except (KeyError, IndexError, TypeError) as exc:
            logger.exception("Unexpected ZAI response shape: %s", data)
            raise RuntimeError("Unexpected ZAI response format") from exc


def _truncate(text: str) -> str:
    if text is None:
        return ""
    if len(text) <= _LOG_MAX_CHARS:
        return text
    return text[:_LOG_MAX_CHARS] + "...[truncated]"


def _serialize_message(message: Message | dict) -> dict:
    if isinstance(message, dict):
        return message
    return message.to_dict()
