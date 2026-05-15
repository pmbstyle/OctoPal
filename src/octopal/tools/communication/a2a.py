from __future__ import annotations

import json
from typing import Any

from octopal.infrastructure.config.models import A2AConfig
from octopal.interop.a2a.client import A2AClientError, send_peer_message


async def a2a_send_message(args: dict[str, Any], ctx: dict[str, Any]) -> str:
    peer_id = str((args or {}).get("peer_id") or "").strip()
    text = str((args or {}).get("text") or "").strip()
    if not peer_id:
        return _json({"status": "error", "message": "peer_id is required."})
    if not text:
        return _json({"status": "error", "message": "text is required."})

    config = _resolve_a2a_config(ctx)
    if not config.enabled:
        return _json({"status": "error", "message": "A2A interop is disabled."})
    try:
        payload = await send_peer_message(config, peer_id=peer_id, text=text)
    except A2AClientError as exc:
        return _json({"status": "error", "message": str(exc)})
    except Exception as exc:
        return _json({"status": "error", "message": f"A2A request failed: {exc}"})
    return _json(
        {
            "status": "ok",
            "peer_id": peer_id,
            "response": payload,
        }
    )


def _resolve_a2a_config(ctx: dict[str, Any]) -> A2AConfig:
    octo = (ctx or {}).get("octo")
    runtime_settings = getattr(getattr(octo, "runtime", None), "settings", None)
    candidate = getattr(runtime_settings, "a2a", None)
    if isinstance(candidate, A2AConfig):
        return candidate
    config_obj = getattr(runtime_settings, "config_obj", None)
    candidate = getattr(config_obj, "a2a", None)
    if isinstance(candidate, A2AConfig):
        return candidate
    return A2AConfig()


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)

