from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog
from broodmind.store.base import Store
from broodmind.utils import utc_now

logger = structlog.get_logger(__name__)

class SchedulerService:
    def __init__(self, store: Store, workspace_dir: Path) -> None:
        self.store = store
        self.workspace_dir = workspace_dir
        self.heartbeat_md = workspace_dir / "HEARTBEAT.md"

    def schedule_task(self, name: str, frequency: str, task_text: str, 
                      description: str | None = None, worker_id: str | None = None, 
                      inputs: dict | None = None) -> str:
        """Add or update a scheduled task."""
        task_id = self._generate_id(name)
        self.store.upsert_scheduled_task(
            task_id=task_id,
            name=name,
            frequency=frequency,
            task_text=task_text,
            description=description,
            worker_id=worker_id,
            inputs=inputs
        )
        self.sync_to_markdown()
        return task_id

    def remove_task(self, task_id: str) -> None:
        self.store.delete_scheduled_task(task_id)
        self.sync_to_markdown()

    def get_actionable_tasks(self) -> list[dict[str, Any]]:
        """Find tasks that are due to run."""
        all_tasks = self.store.get_scheduled_tasks(enabled_only=True)
        now = utc_now()
        actionable = []

        for task in all_tasks:
            if self._should_run(task, now):
                actionable.append(task)
        
        return actionable

    def mark_executed(self, task_id: str) -> None:
        self.store.update_task_last_run(task_id, utc_now())
        self.sync_to_markdown()

    def sync_to_markdown(self) -> None:
        """Update HEARTBEAT.md to reflect the database state."""
        tasks = self.store.get_scheduled_tasks()
        
        lines = ["# HEARTBEAT - Scheduled Tasks\n", "## Tasks\n"]
        
        for t in tasks:
            lines.append(f"### {t['name']}")
            lines.append(f"- **ID**: {t['id']}")
            if t['description']:
                lines.append(f"- **Description**: {t['description']}")
            lines.append(f"- **Frequency**: {t['frequency']}")
            if t['worker_id']:
                lines.append(f"- **Worker**: {t['worker_id']}")
            lines.append(f"- **Task**: {t['task_text']}")
            lines.append(f"- **Last execution**: {t['last_run_at'] or 'Never'}")
            lines.append(f"- **Status**: {'Enabled' if t['enabled'] else 'Disabled'}")
            lines.append("")

        lines.append("## Tracking")
        for t in tasks:
            lines.append(f"- {t['id']}_last_run: {t['last_run_at'] or 'Never'}")

        content = "\n".join(lines)
        try:
            self.heartbeat_md.write_text(content, encoding="utf-8")
        except Exception:
            logger.exception("Failed to sync HEARTBEAT.md")

    def _generate_id(self, name: str) -> str:
        return re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))

    def _should_run(self, task: dict[str, Any], now: datetime) -> bool:
        last_run_str = task.get("last_run_at")
        if not last_run_str:
            return True  # Never run before
            
        last_run = datetime.fromisoformat(last_run_str)
        freq = task["frequency"].lower()

        # Pattern: Every X minutes
        minute_match = re.search(r'every\s+(\d+)\s+minute', freq)
        if minute_match:
            minutes = int(minute_match.group(1))
            return now >= last_run + timedelta(minutes=minutes)

        # Pattern: Every X hours
        hour_match = re.search(r'every\s+(\d+)\s+hour', freq)
        if hour_match:
            hours = int(hour_match.group(1))
            return now >= last_run + timedelta(hours=hours)

        # Pattern: Daily at HH:MM (UTC)
        daily_match = re.search(r'daily\s+at\s+(\d{1,2}):(\d{2})', freq)
        if daily_match:
            target_h = int(daily_match.group(1))
            target_m = int(daily_match.group(2))
            
            # Check if we've already run today after the target time
            target_today = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
            
            # If target time for today hasn't passed yet, we don't run
            if now < target_today:
                return False
                
            # If we haven't run today yet (last run was before today's target time)
            return last_run < target_today

        return False
