from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Message:
    role: str
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class InferenceProvider(Protocol):
    async def complete(self, messages: list[Message | dict], **kwargs: object) -> str: ...
