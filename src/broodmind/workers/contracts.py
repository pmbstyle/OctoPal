from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    scope: str
    read_only: bool = False


class WorkerSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    task: str
    system_prompt: str
    requested_capabilities: list[Capability] = Field(default_factory=list)
    granted_capabilities: list[Capability] = Field(default_factory=list)
    timeout_seconds: int = 300
    memory_limit_mb: int = 256
    lifecycle: str = "ephemeral"
    worker_module: str = "broodmind.workers.reference.web_fetch_worker"
    worker_entrypoint: str = "worker.py"
    worker_files: dict[str, str] = Field(default_factory=dict)


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    content: Any


class ExecutedIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent_id: str
    permit_id: str
    success: bool
    result: str | None = None
    payload_hash_verified: bool = False


class WorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    intents_executed: list[ExecutedIntent] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    escalations: list[str] = Field(default_factory=list)


class WorkerTemplateSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    worker_entrypoint: str = "worker.py"
    worker_files: dict[str, str]
    requested_capabilities: list[Capability] = Field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), indent=2)
