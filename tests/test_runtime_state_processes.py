from __future__ import annotations

import platform
import subprocess
import sys

import pytest

from octopal.runtime import state


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows PID semantics")
def test_windows_is_pid_running_rejects_exited_process() -> None:
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
    process.wait(timeout=5)

    assert state.is_pid_running(process.pid) is False


def test_windows_process_cmdline_parser_reads_cim_json(monkeypatch) -> None:
    monkeypatch.setattr(
        state.subprocess,
        "check_output",
        lambda *args, **kwargs: (
            '[{"ProcessId":123,"CommandLine":"python -m octopal.cli start --foreground"},'
            '{"ProcessId":456,"CommandLine":null}]'
        ),
    )

    assert state._iter_process_cmdlines_windows() == [
        (123, "python -m octopal.cli start --foreground")
    ]


def test_list_octopal_runtime_pids_ignores_non_foreground_uv_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(state.os, "getpid", lambda: 999)
    monkeypatch.setattr(state, "_current_process_ancestry", lambda: set())
    monkeypatch.setattr(
        state,
        "_iter_process_cmdlines",
        lambda: [
            (10, "uv run octopal start"),
            (11, "python -m octopal.cli start --foreground"),
            (12, "uv run octopal start --foreground"),
        ],
    )

    assert state.list_octopal_runtime_pids() == [11, 12]
