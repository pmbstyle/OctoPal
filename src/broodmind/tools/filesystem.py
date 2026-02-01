from __future__ import annotations

from pathlib import Path
from typing import Any


def fs_read(args: dict[str, Any], base_dir: Path) -> str:
    path = str(args.get("path", "")).strip()
    if not path:
        return "fs_read error: path is required."
    target = (base_dir / path).resolve()
    if not _is_within(base_dir, target):
        return "fs_read error: path outside workspace."
    try:
        return target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"fs_read error: {exc}"


def fs_write(args: dict[str, Any], base_dir: Path) -> str:
    path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not path:
        return "fs_write error: path is required."
    target = (base_dir / path).resolve()
    if not _is_within(base_dir, target):
        return "fs_write error: path outside workspace."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return "fs_write ok"
    except Exception as exc:
        return f"fs_write error: {exc}"


def _is_within(base_dir: Path, target: Path) -> bool:
    try:
        base = base_dir.resolve()
        return base == target or base in target.parents
    except Exception:
        return False
