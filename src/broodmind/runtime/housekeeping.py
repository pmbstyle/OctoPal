from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from broodmind.utils import utc_now


@dataclass
class TmpCleanupResult:
    deleted_files: int = 0
    deleted_dirs: int = 0
    errors: int = 0


@dataclass
class CanonRotationResult:
    rotated: bool = False
    archived_file: str | None = None
    deleted_archives: int = 0
    bootstrap_entries: int = 0


def cleanup_workspace_tmp(workspace_dir: Path, *, retention_hours: int) -> TmpCleanupResult:
    result = TmpCleanupResult()
    tmp_dir = workspace_dir / "tmp"
    if retention_hours <= 0 or not tmp_dir.exists():
        return result

    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    files = [p for p in tmp_dir.rglob("*") if p.is_file()]
    for path in files:
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                path.unlink(missing_ok=True)
                result.deleted_files += 1
        except Exception:
            result.errors += 1

    # Remove empty directories deepest-first.
    for directory in sorted([p for p in tmp_dir.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            next(directory.iterdir())
        except StopIteration:
            try:
                directory.rmdir()
                result.deleted_dirs += 1
            except Exception:
                result.errors += 1
        except Exception:
            result.errors += 1

    return result


def rotate_canon_events(
    workspace_dir: Path,
    *,
    max_bytes: int,
    keep_archives: int,
) -> CanonRotationResult:
    result = CanonRotationResult()
    canon_dir = workspace_dir / "memory" / "canon"
    events_file = canon_dir / "events.jsonl"
    if max_bytes <= 0 or keep_archives <= 0 or not events_file.exists():
        return result

    try:
        size = events_file.stat().st_size
    except OSError:
        return result

    if size <= max_bytes:
        return result

    canon_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d%H%M%S")
    archive = canon_dir / f"events.{timestamp}.jsonl"
    events_file.replace(archive)
    result.rotated = True
    result.archived_file = archive.name

    entries: list[str] = []
    for md_file in sorted(canon_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        if not content.strip():
            continue
        entry = {
            "ts": utc_now().isoformat(),
            "filename": md_file.name,
            "mode": "overwrite",
            "content": content,
        }
        entries.append(json.dumps(entry, ensure_ascii=True))

    with events_file.open("w", encoding="utf-8") as handle:
        for line in entries:
            handle.write(line)
            handle.write("\n")
    result.bootstrap_entries = len(entries)

    archives = sorted(
        canon_dir.glob("events.*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in archives[keep_archives:]:
        stale.unlink(missing_ok=True)
        result.deleted_archives += 1

    return result
