from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from octopal.infrastructure.store.sqlite import SQLiteStore
from octopal.runtime.octo.core import Octo
from octopal.runtime.self_control import (
    SELF_RESTART_ACTION,
    SELF_RESTART_REQUESTED_BY,
    append_control_request,
    due_self_restart_requests,
    read_pending_restart_resume,
)
from octopal.runtime.workers import runtime as worker_runtime
from octopal.tools.workers import management as worker_management


class _StoreSettings:
    def __init__(self, state_dir: Path, workspace_dir: Path) -> None:
        self.state_dir = state_dir
        self.workspace_dir = workspace_dir


class _Runtime:
    def __init__(self, settings: _StoreSettings) -> None:
        self.settings = settings


class _Memory:
    async def add_message(self, role: str, content: str, metadata: dict) -> None:
        return None


def test_self_restart_requires_confirmation(tmp_path: Path) -> None:
    settings = _StoreSettings(tmp_path / "data", tmp_path / "workspace")
    store = SQLiteStore(settings)
    octo = Octo(
        provider=object(),
        store=store,
        policy=object(),
        runtime=_Runtime(settings),
        approvals=object(),
        memory=_Memory(),
        canon=object(),
    )

    async def scenario() -> None:
        result = await octo.request_self_restart(42, {"reason": "reload settings"})
        assert result["status"] == "needs_confirmation"

    asyncio.run(scenario())
    assert not (settings.state_dir / "control_requests.jsonl").exists()


def test_self_restart_persists_handoff_resume_and_request(tmp_path: Path) -> None:
    settings = _StoreSettings(tmp_path / "data", tmp_path / "workspace")
    store = SQLiteStore(settings)
    octo = Octo(
        provider=object(),
        store=store,
        policy=object(),
        runtime=_Runtime(settings),
        approvals=object(),
        memory=_Memory(),
        canon=object(),
    )

    async def scenario() -> dict:
        return await octo.request_self_restart(
            42,
            {
                "reason": "reload authorized connectors",
                "goal_now": "Continue connector setup.",
                "next_step": "Verify connector status.",
                "confirm": True,
                "delay_seconds": 3,
            },
        )

    result = asyncio.run(scenario())
    assert result["status"] == "restart_requested"
    assert result["request"]["action"] == SELF_RESTART_ACTION
    assert result["request"]["requested_by"] == SELF_RESTART_REQUESTED_BY
    assert (settings.workspace_dir / "memory" / "handoff.json").exists()

    resume = read_pending_restart_resume(settings.state_dir)
    assert resume is not None
    assert resume["request_id"] == result["request"]["request_id"]
    assert resume["handoff"]["goal_now"] == "Continue connector setup."


def test_due_self_restart_requests_are_octo_only(tmp_path: Path) -> None:
    state_dir = tmp_path / "data"
    append_control_request(
        state_dir,
        action=SELF_RESTART_ACTION,
        reason="ok",
        requested_by=SELF_RESTART_REQUESTED_BY,
        delay_seconds=0,
    )
    append_control_request(
        state_dir,
        action=SELF_RESTART_ACTION,
        reason="wrong source",
        requested_by="worker",
        delay_seconds=0,
    )
    append_control_request(
        state_dir,
        action=SELF_RESTART_ACTION,
        reason="future",
        requested_by=SELF_RESTART_REQUESTED_BY,
        delay_seconds=60,
    )

    due = due_self_restart_requests(
        state_dir,
        now=datetime.now(UTC) + timedelta(seconds=1),
    )
    assert len(due) == 1
    assert due[0]["reason"] == "ok"


def test_workers_cannot_receive_self_restart_tools() -> None:
    assert "octo_restart_self" in worker_runtime._WORKER_BLOCKED_TOOL_NAMES
    assert "self_control" in worker_runtime._WORKER_BLOCKED_TOOL_NAMES
    assert "octo_restart_self" in worker_management._WORKER_BLOCKED_TOOL_NAMES
    assert "self_control" in worker_management._WORKER_BLOCKED_TOOL_NAMES
