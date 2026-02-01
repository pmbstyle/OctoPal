from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from broodmind.intents.registry import IntentValidationError, validate_intent
from broodmind.intents.types import ActionIntent, IntentRequest
from broodmind.policy.engine import PolicyEngine
from broodmind.policy.permits import Permit
from broodmind.store.base import Store
from broodmind.store.models import AuditEvent, IntentRecord, PermitRecord, WorkerRecord
from broodmind.workers.contracts import WorkerResult, WorkerSpec
from broodmind.workers.launcher import WorkerLauncher
from broodmind.workers.sandbox import SoftSandbox

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    store: Store
    policy: PolicyEngine
    workspace_dir: Path
    launcher: WorkerLauncher

    async def run(
        self,
        spec: WorkerSpec,
        approval_requester: Callable[[ActionIntent], Awaitable[bool]] | None = None,
    ) -> WorkerResult:
        logger.info(
            "WorkerRuntime run: id=%s lifecycle=%s module=%s timeout=%ss caps=%s",
            spec.id,
            spec.lifecycle,
            spec.worker_module,
            spec.timeout_seconds,
            len(spec.granted_capabilities),
        )
        worker_dir = self._worker_dir(spec.id)
        workers_root = self._workers_root()
        worker_dir.mkdir(parents=True, exist_ok=True)
        spec_path = worker_dir / "spec.json"
        spec_path.write_text(json.dumps(spec.model_dump(), indent=2), encoding="utf-8")
        logger.debug("WorkerRuntime wrote spec: id=%s path=%s", spec.id, spec_path)
        logger.debug("WorkerRuntime spec: %s", _redact_spec_for_log(spec))
        if spec.worker_files:
            _write_worker_files(worker_dir, spec.worker_files)
            logger.debug(
                "WorkerRuntime wrote worker files: id=%s count=%s",
                spec.id,
                len(spec.worker_files),
            )

        now = _utc_now()
        self._ensure_registry()
        self.store.create_worker(
            WorkerRecord(
                id=spec.id,
                status="started",
                task=spec.task,
                granted_caps=[cap.model_dump() for cap in spec.granted_capabilities],
                created_at=now,
                updated_at=now,
            )
        )
        self._append_audit(
            "worker_spawned",
            correlation_id=spec.id,
            data={"task": spec.task},
        )
        self._update_registry_on_spawn(spec)

        sandbox = SoftSandbox(env_whitelist=_default_env_whitelist())
        env = sandbox.build_env({**os.environ, "PYTHONPATH": _pythonpath()})

        process = await self.launcher.launch(
            spec_path=str(spec_path.resolve()),
            cwd=str(worker_dir),
            env=env,
        )
        logger.info("WorkerRuntime process started: id=%s pid=%s", spec.id, process.pid)
        self.store.update_worker_status(spec.id, "running")
        self._append_audit("worker_started", correlation_id=spec.id)

        try:
            result = await asyncio.wait_for(
                self._read_loop(spec, process, approval_requester),
                timeout=spec.timeout_seconds,
            )
            logger.info("WorkerRuntime result: id=%s summary_len=%s", spec.id, len(result.summary))
            self._append_audit(
                "worker_result",
                correlation_id=spec.id,
                data={"summary": result.summary},
            )
            self._update_registry_on_complete(spec)
            return result
        except asyncio.TimeoutError as exc:
            logger.error("Worker %s timed out", spec.id)
            process.kill()
            self.store.update_worker_status(spec.id, "failed")
            self._append_audit(
                "worker_failed",
                level="error",
                correlation_id=spec.id,
                data={"reason": "timeout"},
            )
            self._update_registry_on_failure(spec, "timeout")
            raise RuntimeError("Worker timed out") from exc
        except Exception:
            self.store.update_worker_status(spec.id, "failed")
            self._append_audit(
                "worker_failed",
                level="error",
                correlation_id=spec.id,
                data={"reason": "exception"},
            )
            self._update_registry_on_failure(spec, "exception")
            raise
        finally:
            if spec.lifecycle == "ephemeral":
                self._cleanup_worker_dir(worker_dir)

    async def _read_loop(
        self,
        spec: WorkerSpec,
        process: asyncio.subprocess.Process,
        approval_requester: Callable[[ActionIntent], Awaitable[bool]] | None,
    ) -> WorkerResult:
        invalid_lines = 0
        max_invalid_lines = 50
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            payload = _safe_parse_json(line)
            if payload is None:
                text_line = line.decode("utf-8", errors="replace").strip()
                if text_line:
                    logger.error("Worker output (non-JSON): %s", text_line)
                    self._append_audit(
                        "worker_invalid_output",
                        level="error",
                        correlation_id=spec.id,
                        data={"line": text_line},
                    )
                invalid_lines += 1
                if invalid_lines >= max_invalid_lines:
                    logger.error("Worker emitted too many invalid lines")
                    process.kill()
                    break
                continue

            msg_type = payload.get("type")
            if msg_type == "log":
                logger.info("Worker %s: %s", spec.id, payload.get("message"))
                continue
            if msg_type == "intent_request":
                self._append_audit(
                    "intent_request_ignored",
                    level="warning",
                    correlation_id=spec.id,
                    data={"reason": "intent_system_disabled"},
                )
                continue
            if msg_type == "intent_executed":
                self._append_audit(
                    "intent_executed_ignored",
                    level="warning",
                    correlation_id=spec.id,
                    data={"reason": "intent_system_disabled"},
                )
                continue
            if msg_type == "result":
                result = WorkerResult.model_validate(payload.get("result", {}))
                self.store.update_worker_status(spec.id, "completed")
                logger.info(
                    "WorkerRuntime received result: id=%s evidence=%s summary_len=%s",
                    spec.id,
                    len(result.evidence),
                    len(result.summary),
                )
                return result

        self.store.update_worker_status(spec.id, "failed")
        logger.error("WorkerRuntime failed: id=%s reason=no_result", spec.id)
        self._append_audit(
            "worker_failed",
            level="error",
            correlation_id=spec.id,
            data={"reason": "no_result"},
        )
        raise RuntimeError("Worker exited without result")

    async def _handle_intent_request(
        self,
        spec: WorkerSpec,
        payload: dict[str, Any],
        process: asyncio.subprocess.Process,
        approval_requester: Callable[[ActionIntent], Awaitable[bool]] | None,
    ) -> None:
        intent_payload = payload.get("intent", {})
        request = IntentRequest.model_validate(intent_payload)
        intent_id = str(uuid.uuid4())
        self._append_audit(
            "intent_requested",
            correlation_id=spec.id,
            data={"intent_id": intent_id, "type": request.type},
        )
        try:
            action_intent = validate_intent(request, worker_id=spec.id, intent_id=intent_id)
        except IntentValidationError as exc:
            self._append_audit(
                "intent_validation_failed",
                level="error",
                correlation_id=spec.id,
                data={"error": str(exc)},
            )
            await self._send_message(
                process, {"type": "permit_denied", "intent_id": intent_id, "reason": str(exc)}
            )
            return

        self.store.save_intent(
            IntentRecord(
                id=action_intent.id,
                worker_id=action_intent.worker_id,
                type=action_intent.type,
                payload=action_intent.payload,
                payload_hash=action_intent.payload_hash,
                risk=action_intent.risk,
                requires_approval=action_intent.requires_approval,
                status="validated",
                created_at=_utc_now(),
            )
        )
        self._append_audit(
            "intent_validated",
            correlation_id=spec.id,
            data={"intent_id": action_intent.id, "type": action_intent.type},
        )

        approval = self.policy.check_intent(action_intent)
        if approval.requires_approval:
            self.store.update_intent_status(action_intent.id, "pending_approval")
            self._append_audit(
                "approval_requested",
                correlation_id=spec.id,
                data={"intent_id": action_intent.id, "type": action_intent.type},
            )
            if not approval_requester:
                self.store.update_intent_status(action_intent.id, "denied")
                self._append_audit(
                    "intent_denied",
                    level="warning",
                    correlation_id=spec.id,
                    data={"intent_id": action_intent.id, "reason": "approval_unavailable"},
                )
                await self._send_message(
                    process,
                    {
                        "type": "permit_denied",
                        "intent_id": action_intent.id,
                        "reason": approval.reason or "approval required",
                    },
                )
                return
            approved = await approval_requester(action_intent)
            if not approved:
                self.store.update_intent_status(action_intent.id, "denied")
                self._append_audit(
                    "intent_denied",
                    level="warning",
                    correlation_id=spec.id,
                    data={"intent_id": action_intent.id, "reason": "user_denied"},
                )
                await self._send_message(
                    process,
                    {
                        "type": "permit_denied",
                        "intent_id": action_intent.id,
                        "reason": "user denied",
                    },
                )
                return

        permit = _build_permit(action_intent)
        self.store.create_permit(
            PermitRecord(
                id=permit.id,
                intent_id=permit.intent_id,
                intent_type=permit.intent_type,
                worker_id=permit.worker_id,
                payload_hash=permit.payload_hash,
                expires_at=permit.expires_at,
                consumed_at=None,
                created_at=_utc_now(),
            )
        )
        self.store.update_intent_status(action_intent.id, "approved")
        self._append_audit(
            "permit_issued",
            correlation_id=spec.id,
            data={"intent_id": action_intent.id, "permit_id": permit.id},
        )
        await self._send_message(
            process,
            {"type": "permit", "permit": permit.model_dump(mode="json")},
        )

    async def _handle_intent_executed(self, payload: dict[str, Any]) -> None:
        permit_id = payload.get("permit_id")
        if not permit_id:
            return
        now = _utc_now()
        permit_record = self.store.get_permit(permit_id, now)
        intent_type = payload.get("intent_type")
        payload_hash = payload.get("payload_hash")
        if not permit_record or not intent_type or not payload_hash:
            self._append_audit(
                "intent_executed_invalid",
                level="error",
                correlation_id=payload.get("intent_id"),
                data={
                    "permit_id": permit_id,
                    "reason": "missing_permit_or_payload_hash_or_intent_type",
                },
            )
            return
        if (
            permit_record.payload_hash != payload_hash
            or permit_record.intent_id != payload.get("intent_id")
            or permit_record.intent_type != intent_type
        ):
            self._append_audit(
                "payload_hash_mismatch",
                level="critical",
                correlation_id=payload.get("intent_id"),
                data={
                    "permit_id": permit_id,
                    "expected": permit_record.payload_hash,
                    "actual": payload_hash,
                },
            )
            return
        consumed = self.store.consume_permit_atomic(permit_id, now)
        self._append_audit(
            "intent_executed",
            correlation_id=payload.get("intent_id"),
            data={
                "permit_id": permit_id,
                "worker_id": payload.get("worker_id"),
                "intent_type": intent_type,
                "payload_hash_verified": True,
                "success": payload.get("success"),
                "result": payload.get("result"),
            },
        )
        self._append_audit(
            "permit_consumed",
            correlation_id=payload.get("intent_id"),
            data={
                "permit_id": permit_id,
                "consumed": consumed,
                "worker_id": payload.get("worker_id"),
            },
        )

    async def _send_message(
        self, process: asyncio.subprocess.Process, message: dict[str, Any]
    ) -> None:
        if not process.stdin:
            return
        line = json.dumps(message) + "\n"
        process.stdin.write(line.encode("utf-8"))
        await process.stdin.drain()

    def _append_audit(
        self,
        event_type: str,
        *,
        level: str = "info",
        correlation_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = AuditEvent(
            id=str(uuid.uuid4()),
            ts=_utc_now(),
            correlation_id=correlation_id,
            level=level,
            event_type=event_type,
            data=data or {},
        )
        self.store.append_audit(event)

    def _workers_root(self) -> Path:
        return self.workspace_dir / "workers"

    def _worker_dir(self, worker_id: str) -> Path:
        return self._workers_root() / worker_id

    def _registry_path(self) -> Path:
        return self._workers_root() / "registry.json"

    def _ensure_registry(self) -> None:
        workers_root = self._workers_root()
        workers_root.mkdir(parents=True, exist_ok=True)
        registry_path = self._registry_path()
        if not registry_path.exists():
            registry_path.write_text("[]", encoding="utf-8")

    def _load_registry(self) -> list[dict[str, Any]]:
        try:
            registry_path = self._registry_path()
            if not registry_path.exists():
                return []
            return json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_registry(self, entries: list[dict[str, Any]]) -> None:
        registry_path = self._registry_path()
        registry_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _update_registry_on_spawn(self, spec: WorkerSpec) -> None:
        entries = self._load_registry()
        entries = [e for e in entries if e.get("id") != spec.id]
        entries.append(
            {
                "id": spec.id,
                "module": spec.worker_module,
                "task": spec.task,
                "created_at": _utc_now().isoformat(),
                "last_used_at": _utc_now().isoformat(),
                "lifecycle": spec.lifecycle,
                "status": "running",
            }
        )
        self._save_registry(entries)

    def _update_registry_on_complete(self, spec: WorkerSpec) -> None:
        entries = self._load_registry()
        updated = []
        for entry in entries:
            if entry.get("id") == spec.id:
                entry = {
                    **entry,
                    "last_used_at": _utc_now().isoformat(),
                    "status": "completed",
                }
            updated.append(entry)
        self._save_registry(updated)

    def _update_registry_on_failure(self, spec: WorkerSpec, reason: str) -> None:
        entries = self._load_registry()
        updated = []
        for entry in entries:
            if entry.get("id") == spec.id:
                entry = {
                    **entry,
                    "last_used_at": _utc_now().isoformat(),
                    "status": "failed",
                    "failure_reason": reason,
                }
            updated.append(entry)
        self._save_registry(updated)

    def _cleanup_worker_dir(self, worker_dir: Path) -> None:
        try:
            if worker_dir.exists():
                shutil.rmtree(worker_dir)
                logger.info("WorkerRuntime cleaned up worker dir: %s", worker_dir)
        except Exception as exc:
            logger.warning("WorkerRuntime cleanup failed: %s", exc)


def _build_permit(action_intent: Any) -> Permit:
    return Permit(
        id=str(uuid.uuid4()),
        intent_id=action_intent.id,
        intent_type=action_intent.type,
        worker_id=action_intent.worker_id,
        payload_hash=action_intent.payload_hash,
        expires_at=_utc_now() + timedelta(seconds=60),
        one_time=True,
        consumed=False,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_parse_json(line: bytes) -> dict[str, Any] | None:
    try:
        return json.loads(line.decode("utf-8"))
    except Exception:
        return None


def _pythonpath() -> str:
    return os.pathsep.join([p for p in sys.path if p])


def _default_env_whitelist() -> list[str]:
    if os.name == "nt":
        return [
            "PATH",
            "PYTHONPATH",
            "SYSTEMROOT",
            "COMSPEC",
            "PATHEXT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "ZAI_API_KEY",
            "ZAI_BASE_URL",
            "ZAI_CHAT_PATH",
            "ZAI_MODEL",
            "ZAI_TIMEOUT_SECONDS",
            "ZAI_CONNECT_TIMEOUT_SECONDS",
            "ZAI_ACCEPT_LANGUAGE",
            "BRAVE_API_KEY",
        ]
    return [
        "PATH",
        "PYTHONPATH",
        "ZAI_API_KEY",
        "ZAI_BASE_URL",
        "ZAI_CHAT_PATH",
        "ZAI_MODEL",
        "ZAI_TIMEOUT_SECONDS",
        "ZAI_CONNECT_TIMEOUT_SECONDS",
        "ZAI_ACCEPT_LANGUAGE",
        "BRAVE_API_KEY",
    ]


def _write_worker_files(worker_dir: Path, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        safe_path = Path(rel_path)
        if safe_path.is_absolute() or ".." in safe_path.parts:
            raise RuntimeError(f"Invalid worker file path: {rel_path}")
        target = worker_dir / safe_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _redact_spec_for_log(spec: WorkerSpec) -> str:
    try:
        data = spec.model_dump()
        system_prompt = data.get("system_prompt", "")
        data["system_prompt"] = f"[len={len(system_prompt)}]"
        task = data.get("task", "")
        if task and len(task) > 200:
            data["task"] = task[:200] + "...[truncated]"
        if "worker_files" in data:
            data["worker_files"] = {k: f"[len={len(v)}]" for k, v in data["worker_files"].items()}
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return "<spec unavailable>"
