from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol


@dataclass(frozen=True)
class Message:
    role: str
    content: str | list[dict[str, Any]]

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class InferenceProvider(Protocol):
    async def complete(self, messages: list[Message | dict], **kwargs: object) -> str: ...

    async def complete_stream(
        self,
        messages: list[Message | dict],
        *,
        on_partial: Callable[[str], Awaitable[None]],
        **kwargs: object,
    ) -> str: ...

    async def complete_with_tools(
        self,
        messages: list[Message | dict],
        *,
        tools: list[dict],
        tool_choice: str = "auto",
        **kwargs: object,
    ) -> dict: ...
