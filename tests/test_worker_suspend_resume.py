from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from octopal.infrastructure.config.settings import Settings
from octopal.infrastructure.store.models import AuditEvent, WorkerRecord
from octopal.runtime.workers.contracts import WorkerResult, WorkerSpec
from octopal.runtime.workers.runtime import WorkerRuntime


class _Store:
    def __init__(self, records: dict[str, list[WorkerRecord | None] | WorkerRecord]) -> None:
        self.records = records
        self.status_updates: list[tuple[str, str]] = []
        self.result_updates: list[tuple[str, str | None]] = []
        self.audit_events: list[AuditEvent] = []

    def get_worker(self, worker_id: str):
        record = self.records.get(worker_id)
        if isinstance(record, list):
            if len(record) > 1:
                return record.pop(0)
            return record[0]
        return record

    def update_worker_status(self, worker_id: str, status: str) -> None:
        self.status_updates.append((worker_id, status))

    def update_worker_result(
        self, worker_id: str, summary=None, output=None, error=None, tools_used=None
    ) -> None:
        self.result_updates.append((worker_id, summary))

    def append_audit(self, event: AuditEvent) -> None:
        self.audit_events.append(event)


class _Policy:
    pass


class _FakeStdin:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def write(self, data: bytes) -> None:
        self.payloads.append(json.loads(data.decode("utf-8").strip()))

    async def drain(self) -> None:
        return None


class _FakeProcess:
    def __init__(self) -> None:
        self.stdin = _FakeStdin()
        self.returncode = None


def _worker_record(worker_id: str, status: str) -> WorkerRecord:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
    return WorkerRecord(
        id=worker_id,
        status=status,
        task="child task",
        granted_caps=[],
        created_at=now,
        updated_at=now,
        summary="child done" if status == "completed" else None,
        output={"ok": True} if status == "completed" else None,
        error="boom" if status == "failed" else None,
    )


def test_runtime_waits_for_transiently_missing_child_before_resuming(
    monkeypatch, tmp_path: Path
) -> None:
    store = _Store({"child-1": [None, _worker_record("child-1", "completed")]})
    runtime = WorkerRuntime(
        store=store,
        policy=_Policy(),
        workspace_dir=tmp_path,
        launcher=object(),
        settings=Settings(),
    )
    process = _FakeProcess()
    spec = WorkerSpec(
        id="parent-1",
        task="coordinate work",
        inputs={},
        system_prompt="s",
        available_tools=["start_child_worker"],
        granted_capabilities=[],
        timeout_seconds=30,
        max_thinking_steps=5,
    )

    async def _fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("octopal.runtime.workers.runtime.asyncio.sleep", _fake_sleep)

    resume = asyncio.run(
        runtime._await_child_batch(
            spec=spec,
            process=process,
            worker_ids=["child-1"],
        )
    )

    assert resume.status == "completed"
    assert resume.completed_count == 1
    assert resume.completed[0].worker_id == "child-1"
    assert store.status_updates == [
        ("parent-1", "waiting_for_children"),
        ("parent-1", "running"),
    ]
    assert process.stdin.payloads[-1]["type"] == "resume_children"
    assert process.stdin.payloads[-1]["child_batch"]["completed"][0]["worker_id"] == "child-1"


def test_runtime_child_wait_resumes_parent_for_instruction_request(tmp_path: Path) -> None:
    child = _worker_record("child-1", "awaiting_instruction").model_copy(
        update={
            "summary": "Awaiting instruction: choose path",
            "output": {
                "instruction_request": {
                    "request_id": "req-1",
                    "worker_id": "child-1",
                    "target": "parent",
                    "question": "Which path should I take?",
                    "context": {"paths": ["a", "b"]},
                    "timeout_seconds": 120,
                    "created_at": "2026-04-18T12:00:00+00:00",
                }
            },
        }
    )
    store = _Store({"child-1": child})
    runtime = WorkerRuntime(
        store=store,
        policy=_Policy(),
        workspace_dir=tmp_path,
        launcher=object(),
        settings=Settings(),
    )
    process = _FakeProcess()
    spec = WorkerSpec(
        id="parent-1",
        task="coordinate work",
        inputs={},
        system_prompt="s",
        available_tools=["start_child_worker", "answer_worker_instruction"],
        granted_capabilities=[],
        timeout_seconds=30,
        max_thinking_steps=5,
    )

    resume = asyncio.run(
        runtime._await_child_batch(
            spec=spec,
            process=process,
            worker_ids=["child-1"],
        )
    )

    assert resume.status == "awaiting_instruction"
    assert resume.awaiting_instruction_count == 1
    assert resume.awaiting_instruction[0].worker_id == "child-1"
    assert store.status_updates == [
        ("parent-1", "waiting_for_children"),
        ("parent-1", "running"),
    ]
    payload = process.stdin.payloads[-1]["child_batch"]
    assert payload["status"] == "awaiting_instruction"
    assert (
        payload["awaiting_instruction"][0]["output"]["instruction_request"]["request_id"] == "req-1"
    )


def test_runtime_answer_instruction_marks_worker_running_before_resume(tmp_path: Path) -> None:
    store = _Store({})
    runtime = WorkerRuntime(
        store=store,
        policy=_Policy(),
        workspace_dir=tmp_path,
        launcher=object(),
        settings=Settings(),
    )

    async def _run() -> str:
        future = asyncio.get_running_loop().create_future()
        runtime._instruction_waiters[("worker-1", "req-1")] = future
        answered = await runtime.answer_instruction(
            worker_id="worker-1",
            request_id="req-1",
            instruction="continue",
        )
        assert answered is True
        return await future

    instruction = asyncio.run(_run())

    assert instruction == "continue"
    assert store.status_updates == [("worker-1", "running")]
    assert store.audit_events[-1].event_type == "worker_instruction_answered"


def test_active_timeout_excludes_paused_worker_time(monkeypatch, tmp_path: Path) -> None:
    runtime = WorkerRuntime(
        store=_Store({}),
        policy=_Policy(),
        workspace_dir=tmp_path,
        launcher=object(),
        settings=Settings(),
    )
    process = _FakeProcess()
    spec = WorkerSpec(
        id="worker-1",
        task="wait then finish",
        inputs={},
        system_prompt="s",
        available_tools=[],
        granted_capabilities=[],
        timeout_seconds=30,
        max_thinking_steps=5,
    )

    async def _fake_read_loop(*args, pause_tracker=None, **kwargs):
        assert pause_tracker is not None
        pause_tracker.pause("waiting_for_children")
        await asyncio.sleep(0.04)
        pause_tracker.resume()
        await asyncio.sleep(0.005)
        return WorkerResult(summary="done")

    monkeypatch.setattr(runtime, "_read_loop", _fake_read_loop)

    result = asyncio.run(
        runtime._read_loop_with_active_timeout(
            spec,
            process,
            approval_requester=None,
            timeout_seconds=0.02,
        )
    )

    assert result.summary == "done"
