from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from broodmind.config.settings import Settings


def _status_path(settings: Settings) -> Path:
    return settings.state_dir / "status.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_start_status(settings: Settings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": _current_pid(),
        "started_at": _utc_now_iso(),
        "last_message_at": None,
    }
    _status_path(settings).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_last_message(settings: Settings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    path = _status_path(settings)
    payload = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    payload["last_message_at"] = _utc_now_iso()
    if "pid" not in payload:
        payload["pid"] = _current_pid()
    if "started_at" not in payload:
        payload["started_at"] = _utc_now_iso()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_status(settings: Settings) -> dict | None:
    path = _status_path(settings)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _current_pid() -> int:
    import os

    return os.getpid()


def is_pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        return _is_pid_running_impl(pid)
    except Exception:
        return False


def _is_pid_running_impl(pid: int) -> bool:
    import os
    import platform

    if platform.system() != "Windows":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    try:
        import ctypes
        import ctypes.wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False
