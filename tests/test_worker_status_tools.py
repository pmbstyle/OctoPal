from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from octopal.infrastructure.store.models import WorkerRecord
from octopal.tools.workers import management


def _worker_record(*, status: str) -> WorkerRecord:
    now = datetime(2026, 4, 16, 20, 54, 30, tzinfo=UTC)
    return WorkerRecord(
        id="worker-1",
        status=status,
        task="test task",
        granted_caps=[],
        created_at=now - timedelta(seconds=45),
        updated_at=now - timedelta(seconds=5),
        summary="done" if status == "completed" else None,
        output={"ok": True} if status == "completed" else None,
        error="boom" if status == "failed" else None,
        lineage_id="lineage-1",
        parent_worker_id="parent-1",
        root_task_id="root-1",
        spawn_depth=1,
        template_id="worker-template",
        template_name="Worker Template",
    )


class _Store:
    def __init__(self, worker: WorkerRecord) -> None:
        self.worker = worker

    def get_worker(self, worker_id: str):
        return self.worker if worker_id == self.worker.id else None


class _Octo:
    def __init__(self, worker: WorkerRecord) -> None:
        self.store = _Store(worker)
        self.runtime = object()


def test_get_worker_status_includes_explicit_timing_fields(monkeypatch) -> None:
    worker = _worker_record(status="running")
    frozen_now = datetime(2026, 4, 16, 20, 54, 30, tzinfo=UTC)
    monkeypatch.setattr(management, "utc_now", lambda: frozen_now)
    payload = management._tool_get_worker_status(
        {"worker_id": worker.id},
        {"octo": _Octo(worker)},
    )
    data = json.loads(payload)
    assert data["status"] == "running"
    assert data["created_at"] == "2026-04-16T20:53:45+00:00"
    assert data["updated_at"] == "2026-04-16T20:54:25+00:00"
    assert data["runtime_seconds"] == 45
    assert data["seconds_since_update"] == 5


def test_get_worker_result_running_includes_explicit_timing_fields(monkeypatch) -> None:
    worker = _worker_record(status="running")
    frozen_now = datetime(2026, 4, 16, 20, 54, 30, tzinfo=UTC)
    monkeypatch.setattr(management, "utc_now", lambda: frozen_now)
    payload = management._tool_get_worker_result(
        {"worker_id": worker.id},
        {"octo": _Octo(worker)},
    )
    data = json.loads(payload)
    assert data["status"] == "running"
    assert data["message"] == "Worker is still running. Result not available yet."
    assert data["runtime_seconds"] == 45
    assert data["seconds_since_update"] == 5


def test_get_worker_result_failed_includes_summary_and_output(monkeypatch) -> None:
    worker = _worker_record(status="failed").model_copy(
        update={
            "summary": "Task failed temporarily: inference provider is currently overloaded.",
            "output": {"retryable": True, "reason": "inference_upstream_unavailable"},
        }
    )
    frozen_now = datetime(2026, 4, 16, 20, 54, 30, tzinfo=UTC)
    monkeypatch.setattr(management, "utc_now", lambda: frozen_now)
    payload = management._tool_get_worker_result(
        {"worker_id": worker.id},
        {"octo": _Octo(worker)},
    )
    data = json.loads(payload)
    assert data["status"] == "failed"
    assert data["summary"] == "Task failed temporarily: inference provider is currently overloaded."
    assert data["output"] == {"retryable": True, "reason": "inference_upstream_unavailable"}
    assert data["error"] == "boom"


def test_get_worker_result_waiting_for_children_has_specific_message(monkeypatch) -> None:
    worker = _worker_record(status="waiting_for_children")
    frozen_now = datetime(2026, 4, 16, 20, 54, 30, tzinfo=UTC)
    monkeypatch.setattr(management, "utc_now", lambda: frozen_now)
    payload = management._tool_get_worker_result(
        {"worker_id": worker.id},
        {"octo": _Octo(worker)},
    )
    data = json.loads(payload)
    assert data["status"] == "waiting_for_children"
    assert data["message"] == "Worker is waiting for child workers to finish before resuming."


def test_get_worker_result_awaiting_instruction_exposes_request(monkeypatch) -> None:
    worker = _worker_record(status="awaiting_instruction").model_copy(
        update={
            "summary": "Awaiting instruction: choose path",
            "output": {
                "instruction_request": {
                    "request_id": "req-1",
                    "worker_id": "worker-1",
                    "target": "octo",
                    "question": "Which path should I take?",
                    "context": {"paths": ["a", "b"]},
                    "timeout_seconds": 120,
                    "created_at": "2026-04-16T20:54:25+00:00",
                }
            },
        }
    )
    frozen_now = datetime(2026, 4, 16, 20, 54, 30, tzinfo=UTC)
    monkeypatch.setattr(management, "utc_now", lambda: frozen_now)
    payload = management._tool_get_worker_result(
        {"worker_id": worker.id},
        {"octo": _Octo(worker)},
    )
    data = json.loads(payload)
    assert data["status"] == "awaiting_instruction"
    assert data["message"] == "Worker is waiting for an instruction before resuming."
    assert data["instruction_request"]["request_id"] == "req-1"
    assert data["instruction_request"]["question"] == "Which path should I take?"
