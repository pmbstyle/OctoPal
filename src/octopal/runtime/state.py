from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from octopal.channels import user_channel_label
from octopal.infrastructure.config.settings import Settings


def _status_path(settings: Settings) -> Path:
    return settings.state_dir / "status.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_start_status(settings: Settings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    now = _utc_now_iso()
    payload = {
        "pid": _current_pid(),
        "started_at": now,
        "status_updated_at": now,
        "last_message_at": None,
        "last_user_message_at": None,
        "last_internal_heartbeat_at": None,
        "last_scheduler_tick_at": None,
        "last_scheduler_tick_status": None,
        "active_channel": user_channel_label(settings.user_channel),
        "phase": "starting",
    }
    _status_path(settings).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_last_message(settings: Settings) -> None:
    update_runtime_status_timestamp(
        settings,
        "last_user_message_at",
        legacy_field="last_message_at",
    )


def update_last_internal_heartbeat(settings: Settings) -> None:
    update_runtime_status_timestamp(settings, "last_internal_heartbeat_at")


def update_last_scheduler_tick(settings: Settings, *, status: str | None = None) -> None:
    extra = {}
    if status is not None:
        extra["last_scheduler_tick_status"] = str(status)
    update_runtime_status_timestamp(settings, "last_scheduler_tick_at", extra=extra)


def update_runtime_status_timestamp(
    settings: Settings,
    field: str,
    *,
    legacy_field: str | None = None,
    extra: dict | None = None,
) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    path = _status_path(settings)
    payload = _read_status_payload(path)
    now = _utc_now_iso()
    payload[field] = now
    payload["status_updated_at"] = now
    if legacy_field:
        payload[legacy_field] = now
    if extra:
        payload.update(extra)
    if "pid" not in payload:
        payload["pid"] = _current_pid()
    if "started_at" not in payload:
        payload["started_at"] = now
    if "active_channel" not in payload:
        payload["active_channel"] = user_channel_label(settings.user_channel)
    payload["phase"] = "running"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def mark_runtime_running(settings: Settings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    path = _status_path(settings)
    payload = _read_status_payload(path)
    now = _utc_now_iso()
    if "pid" not in payload:
        payload["pid"] = _current_pid()
    if "started_at" not in payload:
        payload["started_at"] = now
    if "active_channel" not in payload:
        payload["active_channel"] = user_channel_label(settings.user_channel)
    payload["status_updated_at"] = now
    payload["phase"] = "running"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_status(settings: Settings) -> dict | None:
    path = _status_path(settings)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_status_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_runtime_status_display(
    *, status_data: dict | None, pid_running: bool
) -> tuple[str, str]:
    if not pid_running:
        return "STOPPED", "bright_red"
    phase = str((status_data or {}).get("phase") or "").strip().lower()
    if phase == "starting":
        return "STARTING", "yellow"
    return "RUNNING", "bright_green"


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


def is_octopal_runtime_pid(pid: int | None) -> bool:
    if not pid or not is_pid_running(pid):
        return False
    cmdline = pid_command_line(pid)
    return bool(cmdline and _looks_like_octopal_runtime_cmd(cmdline))


def list_octopal_runtime_pids() -> list[int]:
    """Return running PIDs that look like `octopal start` runtime processes."""
    current_pid = os.getpid()
    excluded = _current_process_ancestry()
    pids: list[int] = []
    for pid, cmdline in _iter_process_cmdlines():
        if pid == current_pid or pid in excluded:
            continue
        if _looks_like_octopal_runtime_cmd(cmdline):
            pids.append(pid)
    # Stable output for user-facing display and deterministic behavior.
    return sorted(set(pids))


def pid_command_line(pid: int) -> str:
    """Best-effort command line lookup for a PID."""
    for found_pid, cmdline in _iter_process_cmdlines():
        if found_pid == pid:
            return cmdline
    return ""


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
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            ctypes.wintypes.DWORD,
            ctypes.wintypes.BOOL,
            ctypes.wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        kernel32.GetExitCodeProcess.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(ctypes.wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = ctypes.wintypes.BOOL

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _looks_like_octopal_runtime_cmd(cmdline: str) -> bool:
    lowered = cmdline.lower()
    executable = _command_executable_name(cmdline)
    if executable not in {
        "octopal",
        "octopal.exe",
        "python",
        "python.exe",
        "python3",
        "python3.exe",
        "pythonw.exe",
    }:
        return False
    # Ignore command wrappers like `uv run octopal start` that invoke this CLI.
    if "uv run octopal start" in lowered and "--foreground" not in lowered:
        return False
    if "octopal.cli start" in lowered:
        return True
    if " octopal start --foreground" in f" {lowered}":
        return True
    return " -m octopal.cli start" in lowered


def _command_executable_name(cmdline: str) -> str:
    stripped = cmdline.strip()
    if not stripped:
        return ""
    if stripped[0] in {'"', "'"}:
        quote = stripped[0]
        end = stripped.find(quote, 1)
        token = stripped[1:end] if end > 1 else stripped[1:]
    else:
        token = stripped.split(maxsplit=1)[0]
    return Path(token).name.lower()


def _iter_process_cmdlines() -> list[tuple[int, str]]:
    import platform

    if platform.system() == "Windows":
        return _iter_process_cmdlines_windows()
    if platform.system() == "Linux":
        return _iter_process_cmdlines_linux_procfs()
    return _iter_process_cmdlines_ps()


def _iter_process_cmdlines_linux_procfs() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    proc = Path("/proc")
    if not proc.exists():
        return rows
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
            continue
        if not raw:
            continue
        parts = [part for part in raw.decode("utf-8", errors="replace").split("\x00") if part]
        if not parts:
            continue
        rows.append((pid, " ".join(parts)))
    return rows


def _iter_process_cmdlines_windows() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    try:
        out = subprocess.check_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return rows
    try:
        parsed = json.loads(out.strip() or "[]")
    except json.JSONDecodeError:
        return rows
    if isinstance(parsed, dict):
        records = [parsed]
    elif isinstance(parsed, list):
        records = parsed
    else:
        return rows
    for record in records:
        if not isinstance(record, dict):
            continue
        try:
            pid = int(record.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        cmdline = record.get("CommandLine")
        if pid > 0 and isinstance(cmdline, str) and cmdline:
            rows.append((pid, cmdline))
    return rows


def _iter_process_cmdlines_ps() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,args="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return rows
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        cmdline = parts[1] if len(parts) > 1 else ""
        rows.append((pid, cmdline))
    return rows


def _current_process_ancestry() -> set[int]:
    import platform

    if platform.system() != "Linux":
        parent = os.getppid()
        return {parent} if parent > 0 else set()

    lineage: set[int] = set()
    pid = os.getpid()
    for _ in range(16):
        ppid = _read_linux_ppid(pid)
        if ppid <= 0 or ppid in lineage:
            break
        lineage.add(ppid)
        pid = ppid
    return lineage


def _read_linux_ppid(pid: int) -> int:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        content = stat_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0
    # Format: pid (comm) state ppid ...
    right_paren = content.rfind(")")
    if right_paren == -1:
        return 0
    tail = content[right_paren + 1 :].strip()
    parts = tail.split()
    if len(parts) < 3:
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0
