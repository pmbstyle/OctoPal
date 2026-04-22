from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from octopal.runtime.octo import core as octo_core
from octopal.runtime.octo.core import Octo
from octopal.runtime.octo import router as octo_router
from octopal.runtime.scheduler.service import SchedulerService
from octopal.runtime.workers.contracts import WorkerResult
from octopal.tools.tools import _tool_check_schedule, _tool_schedule_task, _tool_scheduler_status


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
        metadata: dict | None = None,
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
            "metadata": metadata,
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


class _BrowserStub:
    async def shutdown(self) -> None:
        return None


def test_schedule_task_rejects_invalid_frequency(tmp_path: Path) -> None:
    scheduler = SchedulerService(store=_StoreStub(), workspace_dir=tmp_path)
    result = _tool_schedule_task(
        {
            "name": "Daily digest",
            "frequency": "Every often",
            "task": "Generate digest",
        },
        {"octo": SimpleNamespace(scheduler=scheduler)},
    )
    assert result.startswith("schedule_task error:")


def test_schedule_task_normalizes_valid_frequency(tmp_path: Path) -> None:
    store = _StoreStub()
    scheduler = SchedulerService(store=store, workspace_dir=tmp_path)
    task_id = scheduler.schedule_task(
        name="Digest",
        frequency="daily at 7:05",
        task_text="Generate digest",
        notify_user="always",
    )
    assert task_id == "digest"
    assert store.last_upsert is not None
    assert store.last_upsert["frequency"] == "Daily at 07:05"
    assert store.last_upsert["metadata"] == {"notify_user": "always"}


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
                "metadata_json": json.dumps({"notify_user": "always"}),
                "last_run_at": None,
                "enabled": 1,
            }
        ]
    )
    scheduler = SchedulerService(store=store, workspace_dir=tmp_path)
    payload = json.loads(
        asyncio.run(_tool_check_schedule({}, {"octo": SimpleNamespace(scheduler=scheduler)}))
    )
    assert payload["due_count"] == 1
    assert payload["due_tasks"][0]["task_id"] == "daily_digest"
    assert payload["due_tasks"][0]["inputs"] == {"section": "news", "max_items": 5}
    assert payload["due_tasks"][0]["notify_user"] == "always"


def test_scheduler_status_reports_due_and_next_run_preview(tmp_path: Path) -> None:
    store = _StoreStub(
        tasks=[
            {
                "id": "daily_digest",
                "name": "Daily Digest",
                "description": "Build digest",
                "frequency": "Every 30 minutes",
                "worker_id": "writer",
                "task_text": "Generate a concise digest",
                "inputs_json": json.dumps({"section": "news"}),
                "metadata_json": json.dumps({"notify_user": "if_significant"}),
                "last_run_at": None,
                "enabled": 1,
            },
            {
                "id": "nightly_cleanup",
                "name": "Nightly Cleanup",
                "description": "Compact memory",
                "frequency": "Daily at 23:30",
                "worker_id": None,
                "task_text": "Compact memory",
                "inputs_json": "{}",
                "metadata_json": json.dumps({"notify_user": "never"}),
                "last_run_at": None,
                "enabled": 0,
            },
        ]
    )
    scheduler = SchedulerService(store=store, workspace_dir=tmp_path)
    payload = json.loads(
        asyncio.run(_tool_scheduler_status({}, {"octo": SimpleNamespace(scheduler=scheduler)}))
    )

    assert payload["status"] == "ok"
    assert payload["due_count"] == 1
    assert payload["disabled_count"] == 1
    assert payload["next_due_task"]["task_id"] == "daily_digest"
    assert payload["tasks"][0]["due_now"] is True
    assert payload["tasks"][0]["next_run_at"] is not None
    assert payload["tasks"][0]["notify_user"] == "if_significant"
    assert any("due now" in hint for hint in payload["hints"])


def test_schedule_task_rejects_invalid_notify_user(tmp_path: Path) -> None:
    scheduler = SchedulerService(store=_StoreStub(), workspace_dir=tmp_path)
    result = _tool_schedule_task(
        {
            "name": "Digest",
            "frequency": "Every 30 minutes",
            "task": "Generate digest",
            "notify_user": "sometimes",
        },
        {"octo": SimpleNamespace(scheduler=scheduler)},
    )
    assert result.startswith("schedule_task error:")


def test_octo_marks_scheduled_task_after_successful_worker_run_even_if_store_lags() -> None:
    async def _run(worker_status: str | None) -> list[str]:
        store = _StoreStub(worker_status=worker_status)
        scheduler = SchedulerService(store=store, workspace_dir=Path("."))
        octo = Octo(
            provider=object(),
            store=store,
            policy=object(),
            runtime=_RuntimeStub(),
            approvals=_ApprovalsStub(),
            memory=_MemoryStub(),
            canon=object(),
            scheduler=scheduler,
        )
        await octo._start_worker_async(
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
    marked_missing = asyncio.run(_run(None))
    marked_failed = asyncio.run(_run("failed"))

    assert marked_completed == ["daily_digest"]
    assert marked_missing == ["daily_digest"]
    assert marked_failed == []


@pytest.mark.asyncio
async def test_route_scheduler_tick_uses_control_plane_prompt_and_skips_planner(monkeypatch):
    calls = {"control_prompt": 0, "complete_route": 0}

    class SchedulerStub:
        def get_actionable_tasks(self) -> list[dict]:
            return [
                {
                    "id": "daily_digest",
                    "name": "Daily Digest",
                    "worker_id": "writer",
                    "frequency": "Every 30 minutes",
                    "notify_user": "always",
                    "task_text": "Generate digest",
                }
            ]

        def describe_tasks(self, *, enabled_only: bool = False) -> list[dict]:
            return [
                {
                    "id": "daily_digest",
                    "name": "Daily Digest",
                    "due_now": True,
                    "next_run_at": "2026-04-22T12:00:00+00:00",
                    "notify_user": "always",
                }
            ]

    class DummyOcto:
        provider = object()
        reflection = None
        mcp_manager = None
        scheduler = SchedulerStub()

        async def set_thinking(self, value):
            return None

    async def _build_control_plane_prompt(**kwargs):
        calls["control_prompt"] += 1
        assert kwargs["mode_label"] == "scheduler"
        assert "daily_digest" in kwargs["user_text"]
        return [octo_router.Message(role="system", content="scheduler control plane")]

    async def _complete_route_with_tools(**kwargs):
        calls["complete_route"] += 1
        return "SCHEDULER_IDLE"

    def _build_octo_prompt_should_not_run(*args, **kwargs):
        raise AssertionError("build_octo_prompt should not run for scheduler route")

    def _build_plan_should_not_run(*args, **kwargs):
        raise AssertionError("_build_plan should not run for scheduler route")

    monkeypatch.setattr(octo_router, "build_control_plane_prompt", _build_control_plane_prompt)
    monkeypatch.setattr(octo_router, "_complete_route_with_tools", _complete_route_with_tools)
    monkeypatch.setattr(octo_router, "build_octo_prompt", _build_octo_prompt_should_not_run)
    monkeypatch.setattr(octo_router, "_build_plan", _build_plan_should_not_run)

    result = await octo_router.route_scheduler_tick(DummyOcto())

    assert result == "SCHEDULER_IDLE"
    assert calls == {"control_prompt": 1, "complete_route": 1}


@pytest.mark.asyncio
async def test_octo_run_scheduler_tick_once_uses_bounded_scheduler_route(monkeypatch):
    calls = {"scheduler_tick": 0, "dispatch": 0}

    async def _route_scheduler_tick(octo, chat_id=0, *, max_tasks=10):
        calls["scheduler_tick"] += 1
        assert chat_id == 0
        assert max_tasks == 7
        return "SCHEDULER_IDLE"

    async def _dispatch_due_scheduled_tasks_once(self, *, chat_id=0, max_tasks=10):
        calls["dispatch"] += 1
        assert chat_id == 0
        assert max_tasks == 7
        return {
            "due_count": 0,
            "attempted": 0,
            "started": 0,
            "duplicates": 0,
            "invalid": 0,
            "errors": 0,
        }

    monkeypatch.setattr(octo_router, "route_scheduler_tick", _route_scheduler_tick)
    monkeypatch.setattr(octo_core, "route_scheduler_tick", _route_scheduler_tick)
    monkeypatch.setattr(
        octo_core.Octo,
        "_dispatch_due_scheduled_tasks_once",
        _dispatch_due_scheduled_tasks_once,
    )

    octo = Octo(
        provider=object(),
        store=_StoreStub(),
        policy=object(),
        runtime=_RuntimeStub(),
        approvals=_ApprovalsStub(),
        memory=_MemoryStub(),
        canon=SimpleNamespace(workspace_dir=Path(".")),
        scheduler=SchedulerService(store=_StoreStub(), workspace_dir=Path(".")),
    )

    await octo._run_scheduler_tick_once(max_tasks=7)

    assert calls == {"scheduler_tick": 1, "dispatch": 1}


@pytest.mark.asyncio
async def test_octo_dispatch_due_scheduled_tasks_starts_dispatchable_workers(monkeypatch):
    started_calls = []
    scheduler = SchedulerService(
        store=_StoreStub(
            tasks=[
                {
                    "id": "daily_digest",
                    "name": "Daily Digest",
                    "description": "Build digest",
                    "frequency": "Every 30 minutes",
                    "worker_id": "writer",
                    "task_text": "Generate digest",
                    "inputs_json": json.dumps({"section": "news"}),
                    "metadata_json": json.dumps({"notify_user": "always"}),
                    "last_run_at": None,
                    "enabled": 1,
                }
            ]
        ),
        workspace_dir=Path("."),
    )

    async def _start_worker_async(self, **kwargs):
        started_calls.append(kwargs)
        return {"status": "started", "run_id": "run-1", "worker_id": "run-1"}

    monkeypatch.setattr(octo_core.Octo, "_start_worker_async", _start_worker_async)

    octo = Octo(
        provider=object(),
        store=_StoreStub(),
        policy=object(),
        runtime=_RuntimeStub(),
        approvals=_ApprovalsStub(),
        memory=_MemoryStub(),
        canon=SimpleNamespace(workspace_dir=Path(".")),
        scheduler=scheduler,
    )

    summary = await octo._dispatch_due_scheduled_tasks_once(chat_id=0, max_tasks=5)

    assert summary == {
        "due_count": 1,
        "attempted": 1,
        "started": 1,
        "duplicates": 0,
        "invalid": 0,
        "errors": 0,
    }
    assert started_calls == [
        {
            "worker_id": "writer",
            "task": "Generate digest",
            "chat_id": 0,
            "inputs": {"section": "news"},
            "tools": None,
            "model": None,
            "timeout_seconds": None,
            "scheduled_task_id": "daily_digest",
        }
    ]


@pytest.mark.asyncio
async def test_octo_dispatch_due_scheduled_tasks_skips_invalid_items(monkeypatch):
    scheduler = SchedulerService(
        store=_StoreStub(
            tasks=[
                {
                    "id": "memory_compact",
                    "name": "Memory Compact",
                    "description": "Compact memory",
                    "frequency": "Every 30 minutes",
                    "worker_id": None,
                    "task_text": "Compact memory",
                    "inputs_json": "{}",
                    "metadata_json": json.dumps({"notify_user": "never"}),
                    "last_run_at": None,
                    "enabled": 1,
                }
            ]
        ),
        workspace_dir=Path("."),
    )

    async def _start_worker_async(self, **kwargs):
        raise AssertionError("_start_worker_async should not be called for invalid scheduled items")

    monkeypatch.setattr(octo_core.Octo, "_start_worker_async", _start_worker_async)

    octo = Octo(
        provider=object(),
        store=_StoreStub(),
        policy=object(),
        runtime=_RuntimeStub(),
        approvals=_ApprovalsStub(),
        memory=_MemoryStub(),
        canon=SimpleNamespace(workspace_dir=Path(".")),
        scheduler=scheduler,
    )

    summary = await octo._dispatch_due_scheduled_tasks_once(chat_id=0, max_tasks=5)

    assert summary == {
        "due_count": 1,
        "attempted": 0,
        "started": 0,
        "duplicates": 0,
        "invalid": 1,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_octo_background_tasks_start_and_stop_scheduler_loop(monkeypatch):
    started = {
        "cleanup": 0,
        "metrics": 0,
        "scheduler": 0,
    }

    async def _periodic_cleanup(self, interval_seconds):
        started["cleanup"] += 1
        await asyncio.Event().wait()

    async def _periodic_metrics_publish(self, interval_seconds):
        started["metrics"] += 1
        await asyncio.Event().wait()

    async def _periodic_scheduler_tick(self, interval_seconds, *, max_tasks=10):
        started["scheduler"] += 1
        await asyncio.Event().wait()

    monkeypatch.setattr(octo_core.Octo, "_periodic_cleanup", _periodic_cleanup)
    monkeypatch.setattr(octo_core.Octo, "_periodic_metrics_publish", _periodic_metrics_publish)
    monkeypatch.setattr(octo_core.Octo, "_periodic_scheduler_tick", _periodic_scheduler_tick)
    monkeypatch.setattr(octo_core, "get_browser_manager", lambda: _BrowserStub())

    octo = Octo(
        provider=object(),
        store=_StoreStub(),
        policy=object(),
        runtime=_RuntimeStub(),
        approvals=_ApprovalsStub(),
        memory=_MemoryStub(),
        canon=SimpleNamespace(workspace_dir=Path(".")),
        scheduler=SchedulerService(store=_StoreStub(), workspace_dir=Path(".")),
    )

    octo.start_background_tasks(cleanup_interval_seconds=30, scheduler_interval_seconds=15)
    await asyncio.sleep(0)

    assert octo._cleanup_task is not None
    assert octo._metrics_task is not None
    assert octo._scheduler_task is not None
    assert started == {"cleanup": 1, "metrics": 1, "scheduler": 1}

    await octo.stop_background_tasks()

    assert octo._cleanup_task.cancelled() is True
    assert octo._metrics_task.cancelled() is True
    assert octo._scheduler_task.cancelled() is True
