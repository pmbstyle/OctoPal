from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from broodmind.queen.core import Queen
from broodmind.scheduler.service import SchedulerService
from broodmind.tools.tools import _tool_check_schedule, _tool_schedule_task
from broodmind.workers.contracts import WorkerResult


class _StoreStub:
    def __init__(self, tasks: list[dict] | None = None, worker_status: str | None = None) -> None:
        self.tasks = tasks or []
        self.last_upsert: dict | None = None
        self.marked_task_ids: list[str] = []
        self.worker_status = worker_status

    def upsert_scheduled_task(
        self,
        task_id: str,
        name: str,
        frequency: str,
        task_text: str,
        description: str | None = None,
        worker_id: str | None = None,
        inputs: dict | None = None,
        enabled: bool = True,
    ) -> None:
        self.last_upsert = {
            "task_id": task_id,
            "name": name,
            "frequency": frequency,
            "task_text": task_text,
            "description": description,
            "worker_id": worker_id,
            "inputs": inputs,
            "enabled": enabled,
        }

    def get_scheduled_tasks(self, enabled_only: bool = False) -> list[dict]:
        if not enabled_only:
            return list(self.tasks)
        return [t for t in self.tasks if int(t.get("enabled", 1)) == 1]

    def update_task_last_run(self, task_id: str, _ts) -> None:
        self.marked_task_ids.append(task_id)

    def delete_scheduled_task(self, _task_id: str) -> None:
        return None

    def get_worker(self, _worker_id: str):
        if self.worker_status is None:
            return None
        return SimpleNamespace(status=self.worker_status)


class _MemoryStub:
    async def add_message(self, role: str, text: str, metadata: dict) -> None:
        return None


class _ApprovalsStub:
    bot = None


class _RuntimeStub:
    async def run_task(self, task_request, approval_requester=None):
        return WorkerResult(summary="ok", output={"ok": True})


def test_schedule_task_rejects_invalid_frequency(tmp_path: Path) -> None:
    scheduler = SchedulerService(store=_StoreStub(), workspace_dir=tmp_path)
    result = _tool_schedule_task(
        {
            "name": "Daily digest",
            "frequency": "Every often",
            "task": "Generate digest",
        },
        {"queen": SimpleNamespace(scheduler=scheduler)},
    )
    assert result.startswith("schedule_task error:")


def test_schedule_task_normalizes_valid_frequency(tmp_path: Path) -> None:
    store = _StoreStub()
    scheduler = SchedulerService(store=store, workspace_dir=tmp_path)
    task_id = scheduler.schedule_task(
        name="Digest",
        frequency="daily at 7:05",
        task_text="Generate digest",
    )
    assert task_id == "digest"
    assert store.last_upsert is not None
    assert store.last_upsert["frequency"] == "Daily at 07:05"


def test_check_schedule_returns_json_with_inputs(tmp_path: Path) -> None:
    store = _StoreStub(
        tasks=[
            {
                "id": "daily_digest",
                "name": "Daily Digest",
                "description": "Build digest",
                "frequency": "Every 30 minutes",
                "worker_id": "writer",
                "task_text": "Generate a concise digest",
                "inputs_json": json.dumps({"section": "news", "max_items": 5}),
                "last_run_at": None,
                "enabled": 1,
            }
        ]
    )
    scheduler = SchedulerService(store=store, workspace_dir=tmp_path)
    payload = json.loads(_tool_check_schedule({}, {"queen": SimpleNamespace(scheduler=scheduler)}))
    assert payload["due_count"] == 1
    assert payload["due_tasks"][0]["task_id"] == "daily_digest"
    assert payload["due_tasks"][0]["inputs"] == {"section": "news", "max_items": 5}


def test_queen_marks_scheduled_task_only_on_completed_status() -> None:
    async def _run(worker_status: str) -> list[str]:
        store = _StoreStub(worker_status=worker_status)
        scheduler = SchedulerService(store=store, workspace_dir=Path("."))
        queen = Queen(
            provider=object(),
            store=store,
            policy=object(),
            runtime=_RuntimeStub(),
            approvals=_ApprovalsStub(),
            memory=_MemoryStub(),
            canon=object(),
            scheduler=scheduler,
        )
        await queen._start_worker_async(
            worker_id="writer",
            task="Generate digest",
            chat_id=0,
            inputs={},
            tools=None,
            model=None,
            timeout_seconds=5,
            scheduled_task_id="daily_digest",
        )
        await asyncio.sleep(0.05)
        return store.marked_task_ids

    marked_completed = asyncio.run(_run("completed"))
    marked_failed = asyncio.run(_run("failed"))

    assert marked_completed == ["daily_digest"]
    assert marked_failed == []
