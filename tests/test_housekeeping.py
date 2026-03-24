from __future__ import annotations

from pathlib import Path

from octopal.runtime.housekeeping import cleanup_workspace_tmp, rotate_canon_events


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_cleanup_workspace_tmp_removes_old_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    old_file = workspace / "tmp" / "old.txt"
    new_file = workspace / "tmp" / "new.txt"
    _touch(old_file, "old")
    _touch(new_file, "new")

    # Make old file older than 72h.
    import os
    import time

    old_ts = time.time() - (72 * 3600)
    os.utime(old_file, (old_ts, old_ts))

    result = cleanup_workspace_tmp(workspace, retention_hours=24)
    assert result.deleted_files >= 1
    assert not old_file.exists()
    assert new_file.exists()


def test_rotate_canon_events_bootstraps_snapshot_and_keeps_archives(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    canon_dir = workspace / "memory" / "canon"
    canon_dir.mkdir(parents=True, exist_ok=True)
    (canon_dir / "facts.md").write_text("# Facts\n\nA\n", encoding="utf-8")
    (canon_dir / "decisions.md").write_text("# Decisions\n\nB\n", encoding="utf-8")
    events = canon_dir / "events.jsonl"
    events.write_text('{"ts":"x","filename":"facts.md","mode":"append","content":"c"}\n' * 30, encoding="utf-8")

    # Seed old archives to validate pruning.
    _touch(canon_dir / "events.20250101010101.jsonl", "old1")
    _touch(canon_dir / "events.20250101010102.jsonl", "old2")

    result = rotate_canon_events(
        workspace,
        max_bytes=50,
        keep_archives=2,
    )

    assert result.rotated is True
    assert result.archived_file is not None
    assert result.bootstrap_entries >= 2
    assert events.exists()
    rebuilt = events.read_text(encoding="utf-8")
    assert '"mode": "overwrite"' in rebuilt
    archives = sorted(canon_dir.glob("events.*.jsonl"))
    assert len(archives) <= 2
