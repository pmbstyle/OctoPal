"""
Worker Templates - Now Filesystem-Based

Worker templates are now discovered from the filesystem at runtime.
Templates are stored in: workspace/workers/{worker_id}/worker.json

This module is kept for backwards compatibility but worker templates
are now managed as JSON files in the workspace directory.

Default templates are provided in the source code at:
src/broodmind/workers/default_templates/
"""
from __future__ import annotations

import shutil
from pathlib import Path


def sync_default_templates(workspace_dir: Path, *, overwrite: bool = False) -> dict[str, int]:
    """
    Copy default worker templates into workspace/workers.

    Returns counts:
    - copied: newly copied templates
    - updated: overwritten templates
    - skipped: templates that already existed and were not overwritten
    """
    source_root = Path(__file__).parent / "default_templates"
    target_root = workspace_dir / "workers"
    target_root.mkdir(parents=True, exist_ok=True)

    copied = 0
    updated = 0
    skipped = 0

    for worker_dir in sorted(source_root.iterdir()):
        if not worker_dir.is_dir():
            continue
        src_file = worker_dir / "worker.json"
        if not src_file.exists():
            continue
        dst_dir = target_root / worker_dir.name
        dst_file = dst_dir / "worker.json"
        dst_dir.mkdir(parents=True, exist_ok=True)
        if dst_file.exists():
            if not overwrite:
                skipped += 1
                continue
            shutil.copy2(src_file, dst_file)
            updated += 1
            continue
        shutil.copy2(src_file, dst_file)
        copied += 1

    return {"copied": copied, "updated": updated, "skipped": skipped}


def initialize_templates(store) -> None:
    """
    Initialize default worker templates.

    This is now a no-op since worker templates are auto-discovered
    from the filesystem at: workspace/workers/{id}/worker.json

    Default templates are provided in the source code at:
    src/broodmind/workers/default_templates/

    To add them to your workspace, copy the default_templates directory
    to workspace/workers/

    For Docker:
        docker exec -it <container> python /app/scripts/sync_worker_templates.py

    For direct Python:
        python scripts/sync_worker_templates.py
    """
    # Worker templates are now filesystem-based - no initialization needed
    pass
