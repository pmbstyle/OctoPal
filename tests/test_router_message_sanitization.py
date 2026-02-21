from __future__ import annotations

from broodmind.providers.base import Message
from broodmind.queen.router import _sanitize_messages_for_complete


def test_sanitize_messages_removes_tool_role_and_tool_calls() -> None:
    sanitized = _sanitize_messages_for_complete(
        [
            {"role": "assistant", "content": "thinking", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": '{"ok":true}'},
            {"role": "user", "content": "hello"},
        ]
    )
    roles = [m["role"] for m in sanitized]
    assert "tool" not in roles
    assert roles == ["assistant", "user"]


def test_sanitize_messages_converts_multimodal_content_to_text() -> None:
    sanitized = _sanitize_messages_for_complete(
        [
            Message(
                role="user",
                content=[
                    {"type": "text", "text": "Look at this"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA"}},
                ],
            )
        ]
    )
    assert len(sanitized) == 1
    assert "Look at this" in sanitized[0]["content"]
    assert "image omitted" in sanitized[0]["content"]


def test_sanitize_messages_adds_user_when_missing() -> None:
    sanitized = _sanitize_messages_for_complete(
        [
            Message(role="system", content="Follow strict rules."),
            {"role": "assistant", "content": "Prior tool context"},
        ]
    )
    roles = [m["role"] for m in sanitized]
    assert "user" in roles
