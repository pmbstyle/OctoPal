from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from octopal.runtime.scheduler.service import SchedulerService
from octopal.utils import utc_now

logger = structlog.get_logger(__name__)


def _build_opportunity_card(
    *,
    kind: str,
    title: str,
    why_now: str,
    impact: str,
    effort: str,
    confidence: float,
    next_action: str,
    risk: str = "low",
    suggested_worker_id: str | None = None,
    task: str | None = None,
    dedupe_key: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = {
        "opportunity_id": str(uuid4()),
        "kind": kind,
        "title": title,
        "why_now": why_now,
        "impact": impact,
        "effort": effort,
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "risk": risk if risk in {"low", "medium", "high"} else "low",
        "next_action": next_action,
        "created_at": utc_now().isoformat(),
    }
    if suggested_worker_id:
        card["suggested_worker_id"] = suggested_worker_id
    if task:
        card["task"] = task
    if dedupe_key:
        card["dedupe_key"] = dedupe_key
    if inputs:
        card["inputs"] = inputs
    return card


def _active_self_queue_dedupe_keys(queue: list[dict[str, Any]]) -> set[str]:
    active_statuses = {"pending", "claimed", "running"}
    return {
        str(item.get("dedupe_key") or "").strip()
        for item in queue
        if str(item.get("dedupe_key") or "").strip()
        and str(item.get("status", "pending") or "pending").strip().lower() in active_statuses
    }


def _scheduler_opportunity_cards(
    scheduler: SchedulerService | None,
    queue: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if scheduler is None:
        return []
    try:
        tasks = scheduler.describe_tasks(enabled_only=True)
    except Exception:
        logger.debug("Unable to scan scheduler opportunities", exc_info=True)
        return []

    active_dedupe_keys = _active_self_queue_dedupe_keys(queue)
    cards: list[dict[str, Any]] = []
    for scheduled_task in tasks:
        task_id = str(scheduled_task.get("id") or "").strip()
        if not task_id:
            continue
        suggested_mode = str(scheduled_task.get("suggested_execution_mode") or "").strip().lower()
        if suggested_mode != "worker":
            continue
        dedupe_key = f"scheduled-task:{task_id}:suggested-worker"
        if dedupe_key in active_dedupe_keys:
            continue

        name = str(scheduled_task.get("name") or task_id).strip()
        worker_id = str(scheduled_task.get("worker_id") or "").strip() or "ops_sre"
        blocked_reason = str(
            scheduled_task.get("blocked_reason")
            or scheduled_task.get("dispatch_policy_reason")
            or "suggested_execution_mode=worker"
        ).strip()
        cards.append(
            _build_opportunity_card(
                kind="scheduled_task_repair",
                title=f"Unblock scheduled task: {name}",
                why_now=f"task_id={task_id}, reason={blocked_reason}",
                impact="high",
                effort="medium",
                confidence=0.88,
                risk="medium",
                suggested_worker_id=worker_id,
                task=(
                    f"Inspect scheduled task {task_id!r} ({name!r}) blocked from its current route. "
                    "Find the least-risk repair or migration path, verify whether worker execution is appropriate, "
                    "and report the exact recommended change."
                ),
                dedupe_key=dedupe_key,
                inputs={
                    "scheduled_task_id": task_id,
                    "blocked_reason": blocked_reason,
                    "suggested_execution_mode": suggested_mode,
                },
                next_action="Queue a diagnostic repair item with the suggested worker and dedupe key.",
            )
        )
    return cards


def _self_queue_opportunity_cards(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_dedupe_keys = _active_self_queue_dedupe_keys(queue)
    cards: list[dict[str, Any]] = []
    stale_before = utc_now() - timedelta(hours=6)
    for item in queue:
        status = str(item.get("status", "pending") or "pending").strip().lower()
        if status != "claimed":
            continue
        updated_at = _parse_iso_datetime(item.get("updated_at"))
        if updated_at is None or updated_at > stale_before:
            continue
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            continue
        dedupe_key = f"self-queue:{task_id}:stale-claimed"
        if dedupe_key in active_dedupe_keys:
            continue
        title = str(item.get("title") or task_id).strip()
        cards.append(
            _build_opportunity_card(
                kind="self_queue_recovery",
                title=f"Recover stale self-queue item: {title}",
                why_now=f"task_id={task_id}, status=claimed, updated_at={updated_at.isoformat()}",
                impact="medium",
                effort="low",
                confidence=0.83,
                risk="low",
                task=(
                    f"Review stale claimed self-queue item {task_id!r}; either execute it if still valid, "
                    "or mark it blocked/cancelled with a concise reason."
                ),
                dedupe_key=dedupe_key,
                inputs={"self_queue_task_id": task_id, "stale_status": status},
                next_action="Use octo_self_queue_update or execute_self_queue_item to resolve the stale claim.",
            )
        )
    return cards


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _persist_self_queue(workspace_dir: Path, chat_id: int, queue: list[dict[str, Any]]) -> str:
    memory_dir = workspace_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / f"self-queue-{chat_id}.json"
    path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _load_self_queue(workspace_dir: Path, chat_id: int) -> list[dict[str, Any]]:
    path = (workspace_dir / "memory" / f"self-queue-{chat_id}.json").resolve()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    items: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict) and str(item.get("task_id", "")).strip():
            items.append(dict(item))
    items.sort(key=lambda i: (-int(i.get("priority", 3) or 3), str(i.get("created_at", ""))))
    return items


def _persist_last_opportunities(
    workspace_dir: Path, chat_id: int, opportunities: list[dict[str, Any]]
) -> str:
    memory_dir = workspace_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / f"opportunities-{chat_id}.json"
    path.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
