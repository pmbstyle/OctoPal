from __future__ import annotations

import time

from octopal.runtime.octo.runtime_config import _env_int

_RECENT_WORKER_TASK_TTL_SECONDS = float(
    _env_int(
        "OCTOPAL_RECENT_WORKER_TASK_TTL_SECONDS",
        1800,
        minimum=60,
    )
)


class OctoRecentTaskRuntimeMixin:
    def _reserve_recent_task(
        self,
        *,
        chat_id: int,
        correlation_id: str | None,
        task_signature: str,
    ) -> bool:
        self._prune_recent_tasks()
        scope_id = str(correlation_id or f"chat:{chat_id}")
        key = (chat_id, scope_id, task_signature)
        if key in self._recent_tasks:
            return False
        self._recent_tasks[key] = time.monotonic()
        return True

    def _release_recent_task(
        self,
        *,
        chat_id: int,
        correlation_id: str | None,
        task_signature: str,
    ) -> None:
        scope_id = str(correlation_id or f"chat:{chat_id}")
        self._recent_tasks.pop((chat_id, scope_id, task_signature), None)

    def _prune_recent_tasks(self) -> None:
        now = time.monotonic()
        cutoff = now - _RECENT_WORKER_TASK_TTL_SECONDS
        stale_keys = [key for key, seen_at in self._recent_tasks.items() if seen_at < cutoff]
        for key in stale_keys:
            self._recent_tasks.pop(key, None)
