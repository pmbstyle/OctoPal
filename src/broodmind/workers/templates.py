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
        docker exec -it <container> python /app/scripts/setup_workers.py

    For direct Python:
        python3 scripts/setup_workers.py
    """
    # Worker templates are now filesystem-based - no initialization needed
    pass
