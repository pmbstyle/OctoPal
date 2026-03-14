from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class IntentRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    payload: dict[str, Any]


class ActionIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: str
    payload: dict[str, Any]
    payload_hash: str
    risk: str
    requires_approval: bool
    worker_id: str
