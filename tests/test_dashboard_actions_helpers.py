from __future__ import annotations

import json
from datetime import UTC, datetime

from broodmind.gateway.dashboard import _clear_control_queue_requests, _select_retry_target
from broodmind.infrastructure.store.models import WorkerRecord


def _worker(worker_id: str, status: str) -> WorkerRecord:
    now = datetime.now(UTC)
    return WorkerRecord(
        id=worker_id,
        status=status,
        task="demo task",
        granted_caps=[],
        created_at=now,
        updated_at=now,
    )


def test_select_retry_target_prefers_requested_failed_worker() -> None:
    workers = [_worker("w1", "failed"), _worker("w2", "failed")]
    picked = _select_retry_target(workers, requested_worker_id="w2")
    assert picked is not None
    assert picked.id == "w2"


def test_clear_control_queue_requests_acks_only_pending(tmp_path) -> None:
    state_dir = tmp_path
    req_file = state_dir / "control_requests.jsonl"
    ack_file = state_dir / "control_acks.jsonl"
    req_file.write_text(
        "\n".join(
            [
                json.dumps({"request_id": "r1", "action": "restart_service"}),
                json.dumps({"request_id": "r2", "action": "reload_config"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ack_file.write_text(json.dumps({"request_id": "r1", "status": "ok"}) + "\n", encoding="utf-8")

    cleared = _clear_control_queue_requests(state_dir, actor="tester")
    assert cleared == 1

    lines = [line for line in ack_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    last = json.loads(lines[-1])
    assert last["request_id"] == "r2"
    assert last["status"] == "cleared"
