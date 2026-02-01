from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from broodmind.queen.core import Queen
from broodmind.telegram.approvals import ApprovalManager


@dataclass
class WsApprovalManager:
    send: Callable[[dict[str, Any]], Awaitable[None]]
    timeout_seconds: int = 60
    _pending: Dict[str, asyncio.Future] = field(default_factory=dict)

    async def request_approval(self, intent) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[intent.id] = future
        await self.send(
            {
                "type": "approval_request",
                "intent": intent.model_dump(),
            }
        )
        try:
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            self._pending.pop(intent.id, None)
            return False

    def resolve(self, intent_id: str, approved: bool) -> bool:
        future = self._pending.pop(intent_id, None)
        if not future or future.done():
            return False
        future.set_result(approved)
        return True


def register_ws_routes(app: FastAPI) -> None:
    @app.websocket("/ws")
    async def websocket_endpoint(socket: WebSocket) -> None:
        await socket.accept()
        approvals = WsApprovalManager(send=lambda payload: socket.send_json(payload))
        queen = Queen(
            provider=app.state.provider,
            store=app.state.store,
            policy=app.state.policy,
            runtime=app.state.runtime,
            approvals=ApprovalManager(bot=None),
            memory=app.state.memory,
        )
        tasks: set[asyncio.Task] = set()
        try:
            while True:
                message = await socket.receive_json()
                msg_type = message.get("type")
                if msg_type == "message":
                    task = asyncio.create_task(_handle_message(socket, queen, approvals, message))
                    tasks.add(task)
                    task.add_done_callback(lambda t: tasks.discard(t))
                    continue
                if msg_type == "approval_response":
                    approvals.resolve(
                        str(message.get("intent_id")),
                        bool(message.get("approved")),
                    )
                    continue
                if msg_type == "ping":
                    await socket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            for task in tasks:
                task.cancel()


async def _handle_message(
    socket: WebSocket,
    queen: Queen,
    approvals: WsApprovalManager,
    payload: dict[str, Any],
) -> None:
    text = str(payload.get("text", ""))
    chat_id = int(payload.get("chat_id", 0))
    try:
        response = await queen.handle_message(
            text,
            chat_id,
            approval_requester=approvals.request_approval,
        )
    except Exception as exc:
        response = f"Error: {exc}"
    await socket.send_json({"type": "message", "text": response})
