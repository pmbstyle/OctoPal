from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from octopal.infrastructure.config.settings import load_settings
from octopal.infrastructure.jsonl import read_jsonl_dicts

CONTROL_REQUESTS_FILE = "control_requests.jsonl"
CONTROL_ACKS_FILE = "control_acks.jsonl"
PENDING_RESTART_RESUME_FILE = "pending_restart_resume.json"
SELF_RESTART_ACTION = "restart_service"
SELF_RESTART_REQUESTED_BY = "octo_self_restart"


def append_control_request(
    state_dir: Path,
    *,
    action: str,
    reason: str,
    requested_by: str,
    delay_seconds: int = 5,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    created_at = datetime.now(UTC)
    item = {
        "request_id": request_id,
        "created_at": created_at.isoformat(),
        "not_before": (created_at + timedelta(seconds=max(0, int(delay_seconds)))).isoformat(),
        "action": action,
        "reason": reason,
        "requested_by": requested_by,
        "metadata": dict(metadata or {}),
    }
    _append_jsonl(state_dir / CONTROL_REQUESTS_FILE, item)
    return item


def append_control_ack(
    state_dir: Path,
    request_id: str,
    *,
    status: str,
    source: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "request_id": request_id,
        "acked_at": datetime.now(UTC).isoformat(),
        "status": status,
        "source": source,
        "message": message,
        "metadata": dict(metadata or {}),
    }
    _append_jsonl(state_dir / CONTROL_ACKS_FILE, item)
    return item


def list_unacked_control_requests(state_dir: Path) -> list[dict[str, Any]]:
    requests = _read_jsonl(state_dir / CONTROL_REQUESTS_FILE)
    acks = _read_jsonl(state_dir / CONTROL_ACKS_FILE)
    acked_ids = {str(item.get("request_id", "")).strip() for item in acks}
    return [
        item
        for item in requests
        if str(item.get("request_id", "")).strip()
        and str(item.get("request_id", "")).strip() not in acked_ids
    ]


def due_self_restart_requests(
    state_dir: Path, *, now: datetime | None = None
) -> list[dict[str, Any]]:
    current = now or datetime.now(UTC)
    due: list[dict[str, Any]] = []
    for item in list_unacked_control_requests(state_dir):
        if str(item.get("action", "")).strip() != SELF_RESTART_ACTION:
            continue
        if str(item.get("requested_by", "")).strip() != SELF_RESTART_REQUESTED_BY:
            continue
        not_before = _parse_datetime(str(item.get("not_before", "") or ""))
        if not_before is not None and not_before > current:
            continue
        due.append(item)
    return due


def write_pending_restart_resume(state_dir: Path, payload: dict[str, Any]) -> Path:
    path = state_dir / PENDING_RESTART_RESUME_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_pending_restart_resume(state_dir: Path) -> dict[str, Any] | None:
    path = state_dir / PENDING_RESTART_RESUME_FILE
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def mark_restart_resume_consumed(state_dir: Path) -> None:
    path = state_dir / PENDING_RESTART_RESUME_FILE
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    payload["consumed_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def launch_restart_helper(
    state_dir: Path,
    *,
    request_id: str,
    project_root: Path,
    delay_seconds: int = 1,
) -> None:
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    src_dir = project_root / "src"
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pp}" if existing_pp else str(src_dir)
    env["OCTOPAL_SKIP_VERSION_CHECK"] = "1"
    args = [
        sys.executable,
        "-m",
        "octopal.runtime.self_control",
        "--request-id",
        request_id,
        "--project-root",
        str(project_root),
        "--state-dir",
        str(state_dir),
        "--delay-seconds",
        str(max(0, int(delay_seconds))),
    ]
    with (
        open(log_dir / "self_restart_stdout.log", "a", encoding="utf-8") as out_file,
        open(log_dir / "self_restart_stderr.log", "a", encoding="utf-8") as err_file,
    ):
        if platform.system() == "Windows":
            subprocess.Popen(
                args,
                cwd=str(project_root),
                env=env,
                stdout=out_file,
                stderr=err_file,
                stdin=subprocess.DEVNULL,
                creationflags=0x00000008,
                close_fds=False,
            )
        else:
            subprocess.Popen(
                args,
                cwd=str(project_root),
                env=env,
                stdout=out_file,
                stderr=err_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )


def run_restart_helper(
    *,
    request_id: str,
    project_root: Path,
    state_dir: Path,
    delay_seconds: int,
) -> int:
    append_control_ack(
        state_dir,
        request_id,
        status="helper_started",
        source="self_restart_helper",
        message="Restart helper started.",
    )
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    command = [sys.executable, "-m", "octopal.cli", "restart"]
    env = os.environ.copy()
    src_dir = project_root / "src"
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pp}" if existing_pp else str(src_dir)
    env["OCTOPAL_SKIP_VERSION_CHECK"] = "1"
    try:
        proc = subprocess.run(
            command,
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        append_control_ack(
            state_dir,
            request_id,
            status="error",
            source="self_restart_helper",
            message=str(exc),
        )
        return 1
    append_control_ack(
        state_dir,
        request_id,
        status="executed",
        source="self_restart_helper",
        message="Restart command completed.",
        metadata={
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
        },
    )
    return proc.returncode


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows, _report = read_jsonl_dicts(path, repair=True)
    return rows


def _append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--project-root", default=str(_project_root()))
    parser.add_argument("--state-dir", default="")
    parser.add_argument("--delay-seconds", type=int, default=1)
    args = parser.parse_args()
    state_dir = Path(args.state_dir).resolve() if args.state_dir else load_settings().state_dir
    return run_restart_helper(
        request_id=str(args.request_id),
        project_root=Path(args.project_root).resolve(),
        state_dir=state_dir,
        delay_seconds=int(args.delay_seconds),
    )


if __name__ == "__main__":
    raise SystemExit(main())
