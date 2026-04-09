from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from octopal.gateway.ws import _resolve_ws_chat_id, register_ws_routes


def test_resolve_ws_chat_id_returns_positive_when_no_allowlist() -> None:
    settings = SimpleNamespace(allowed_telegram_chat_ids="")
    assert _resolve_ws_chat_id(settings) > 0


def test_resolve_ws_chat_id_uses_first_allowed_id_when_valid() -> None:
    settings = SimpleNamespace(allowed_telegram_chat_ids="42,100")
    assert _resolve_ws_chat_id(settings) == 42


def test_new_websocket_connection_takes_over_previous_session() -> None:
    class DummyOcto:
        def __init__(self) -> None:
            self.owner: str | None = None

        def set_output_channel(self, is_ws: bool, **kwargs) -> bool:
            owner_id = kwargs.get("owner_id")
            force = bool(kwargs.get("force"))
            if is_ws:
                if self.owner and owner_id and self.owner != owner_id and not force:
                    return False
                self.owner = owner_id
                return True
            if self.owner and owner_id and self.owner != owner_id and not force:
                return False
            self.owner = None
            return True

    app = FastAPI()
    app.state.settings = SimpleNamespace(tailscale_ips="testclient", allowed_telegram_chat_ids="")
    app.state.octo = DummyOcto()
    register_ws_routes(app)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws_one:
            with client.websocket_connect("/ws") as ws_two:
                payload = ws_one.receive_json()
                assert payload["type"] == "warning"
                assert "took over" in payload["message"]
                ws_two.send_json({"type": "ping"})
                assert ws_two.receive_json() == {"type": "pong"}
