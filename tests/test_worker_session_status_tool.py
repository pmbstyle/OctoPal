from __future__ import annotations

import json
from datetime import timedelta

from octopal.tools.workers.management import _tool_worker_session_status
from octopal.utils import utc_now


class _WorkerStub:
    def __init__(
        self,
        *,
        worker_id: str,
        status: str,
        task: str,
        lineage_id: str | None = None,
        parent_worker_id: str | None = None,
        spawn_depth: int = 0,
        summary: str | None = None,
        error: str | None = None,
    ) -> None:
        now = utc_now()
        self.id = worker_id
        self.status = status
        self.task = task
        self.lineage_id = lineage_id
        self.parent_worker_id = parent_worker_id
        self.root_task_id = lineage_id
        self.spawn_depth = spawn_depth
        self.created_at = now - timedelta(minutes=5)
        self.updated_at = now
        self.summary = summary
        self.error = error


class _StoreStub:
    def __init__(self) -> None:
        self._active = [
            _WorkerStub(worker_id="w1", status="running", task="Fetch docs", lineage_id="lin-1"),
            _WorkerStub(
                worker_id="w2",
                status="running",
                task="Parse page",
                lineage_id="lin-1",
                parent_worker_id="w1",
                spawn_depth=1,
            ),
        ]
        self._recent = [
            self._active[0],
            self._active[1],
            _WorkerStub(worker_id="w3", status="failed", task="Summarize", error="timeout"),
        ]

    def get_active_workers(self, older_than_minutes: int = 10):
        return list(self._active)

    def list_recent_workers(self, limit: int = 100):
        return list(self._recent[:limit])


class _OctoStub:
    def __init__(self) -> None:
        self.store = _StoreStub()
        self.runtime = None


def test_worker_session_status_summarizes_fabric_state() -> None:
    payload = json.loads(_tool_worker_session_status({}, {"octo": _OctoStub()}))

    assert payload["status"] == "ok"
    assert payload["active_count"] == 2
    assert payload["status_counts"]["running"] == 2
    assert payload["active_lineages"][0] == {"lineage_id": "lin-1", "active_workers": 2}
    assert any("in flight" in hint for hint in payload["hints"])
    assert any("child-worker lineage" in hint for hint in payload["hints"])


def test_worker_session_status_mentions_recent_failures() -> None:
    payload = json.loads(_tool_worker_session_status({"recent_limit": 5}, {"octo": _OctoStub()}))

    assert any(worker["worker_id"] == "w3" for worker in payload["recent_workers"])
    assert any("failed" in hint for hint in payload["hints"])
