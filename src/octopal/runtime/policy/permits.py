from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Permit(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    intent_id: str
    intent_type: str
    worker_id: str
    payload_hash: str
    expires_at: datetime
    one_time: bool = True
    consumed: bool = False

    def validate_execution(self, intent_type: str, payload_hash: str, now: datetime) -> bool:
        if self.consumed:
            return False
        if now > self.expires_at:
            return False
        if self.intent_type != intent_type:
            return False
        return payload_hash == self.payload_hash


class ApprovalRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    requires_approval: bool
    reason: str | None = None


class PolicyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str | None = None
    audit_level: str = "info"
