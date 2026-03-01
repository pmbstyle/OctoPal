from __future__ import annotations

import json
import math
import os
from uuid import uuid4
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from broodmind.config.settings import Settings
from broodmind.runtime_metrics import read_metrics_snapshot
from broodmind.state import is_pid_running, read_status
from broodmind.store.sqlite import SQLiteStore
from broodmind.store.models import AuditEvent, WorkerRecord

_WINDOW_CHOICES = {15, 60, 240, 1440}
_SERVICE_CHOICES = {"all", "gateway", "queen", "telegram", "exec_run", "mcp", "workers"}


@dataclass(frozen=True)
class DashboardFilters:
    window_minutes: int
    service: str
    environment: str


def register_dashboard_routes(app: FastAPI) -> None:
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page() -> str:
        return _dashboard_html()

    @app.get("/api/dashboard/snapshot")
    async def dashboard_snapshot(
        request: Request,
        last: int = Query(8, ge=1, le=50),
        window_minutes: int = Query(60, ge=1, le=1440),
        service: str = Query("all"),
        environment: str = Query("all"),
    ) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        store = _get_store(app, settings)
        filters = _build_filters(settings, window_minutes=window_minutes, service=service, environment=environment)
        return _build_snapshot(settings, store, last, filters)

    @app.get("/api/dashboard/logs")
    async def dashboard_logs(
        request: Request,
        lines: int = Query(50, ge=1, le=500),
        window_minutes: int = Query(60, ge=1, le=1440),
        service: str = Query("all"),
        environment: str = Query("all"),
    ) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        filters = _build_filters(settings, window_minutes=window_minutes, service=service, environment=environment)
        log_path = settings.state_dir / "logs" / "broodmind.log"
        entries: list[dict[str, str]] = []
        for entry in _collect_logs(log_path, max_lines=1000, filters=filters):
            entries.append(
                {
                    "event": str(entry.get("event", ""))[:200],
                    "level": str(entry.get("level", "info")),
                    "timestamp": str(entry.get("timestamp", "")),
                    "service": str(entry.get("service", "unknown")),
                    "environment": str(entry.get("environment", filters.environment)),
                }
            )
            if len(entries) >= lines:
                break
        return {"count": len(entries), "entries": entries, "filters": _filters_payload(filters, settings)}

    @app.get("/api/dashboard/settings")
    async def dashboard_settings(request: Request) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        return {
            "gateway_host": settings.gateway_host,
            "gateway_port": settings.gateway_port,
            "state_dir": str(settings.state_dir),
            "workspace_dir": str(settings.workspace_dir),
            "log_level": settings.log_level,
            "tailscale_ips_configured": bool(settings.tailscale_ips.strip()),
            "dashboard_token_configured": bool(settings.dashboard_token.strip()),
        }

    @app.post("/api/dashboard/actions")
    async def dashboard_actions(
        request: Request,
        payload: dict[str, Any] = Body(default={}),
    ) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        store = _get_store(app, settings)

        action = str(payload.get("action", "")).strip().lower()
        confirm = bool(payload.get("confirm", False))
        reason = str(payload.get("reason", "")).strip()
        requested_by = str(payload.get("requested_by", "dashboard")).strip() or "dashboard"
        worker_id = str(payload.get("worker_id", "")).strip() or None

        if action not in {"restart_worker", "retry_failed", "clear_control_queue"}:
            raise HTTPException(status_code=400, detail="Unsupported action")
        if action in {"restart_worker", "clear_control_queue"} and not confirm:
            raise HTTPException(status_code=400, detail="Confirmation required")

        result = await _execute_dashboard_action(
            app=app,
            settings=settings,
            store=store,
            action=action,
            worker_id=worker_id,
            reason=reason,
            requested_by=requested_by,
        )
        return result

    @app.get("/api/dashboard/actions/history")
    async def dashboard_actions_history(
        request: Request,
        limit: int = Query(15, ge=1, le=100),
    ) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        store = _get_store(app, settings)
        return {"count": min(limit, 100), "entries": _list_dashboard_action_history(store, limit=limit)}


def _get_settings(app: FastAPI) -> Settings:
    settings = getattr(app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise HTTPException(status_code=500, detail="Settings not initialized")
    return settings


def _get_store(app: FastAPI, settings: Settings) -> SQLiteStore:
    store = getattr(app.state, "dashboard_store", None)
    if isinstance(store, SQLiteStore):
        return store
    store = SQLiteStore(settings)
    app.state.dashboard_store = store
    return store


def _build_filters(settings: Settings, *, window_minutes: int, service: str, environment: str) -> DashboardFilters:
    normalized_window = window_minutes if window_minutes in _WINDOW_CHOICES else 60
    normalized_service = service.strip().lower()
    if normalized_service not in _SERVICE_CHOICES:
        normalized_service = "all"
    env = environment.strip().lower()
    current_env = _resolve_environment(settings)
    if not env:
        env = "all"
    if env == "current":
        env = current_env
    return DashboardFilters(window_minutes=normalized_window, service=normalized_service, environment=env)


def _resolve_environment(settings: Settings) -> str:
    candidate = (
        os.getenv("BROODMIND_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or "local"
    )
    raw = str(candidate or "local").strip().lower()
    return "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"}) or "local"


def _filters_payload(filters: DashboardFilters, settings: Settings) -> dict[str, Any]:
    current_env = _resolve_environment(settings)
    environments = ["all", current_env, "dev", "staging", "prod"]
    deduped: list[str] = []
    for item in environments:
        if item not in deduped:
            deduped.append(item)
    return {
        "window_minutes": filters.window_minutes,
        "service": filters.service,
        "environment": filters.environment,
        "options": {
            "window_minutes": sorted(_WINDOW_CHOICES),
            "service": sorted(_SERVICE_CHOICES),
            "environment": deduped,
        },
        "current_environment": current_env,
    }


def _verify_dashboard_token(request: Request, settings: Settings) -> None:
    expected = settings.dashboard_token.strip()
    if not expected:
        return

    header_token = request.headers.get("x-broodmind-token", "").strip()
    auth_header = request.headers.get("authorization", "").strip()
    bearer_token = ""
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()
    query_token = str(request.query_params.get("token", "")).strip()

    provided = header_token or bearer_token or query_token
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid dashboard token")


async def _execute_dashboard_action(
    *,
    app: FastAPI,
    settings: Settings,
    store: SQLiteStore,
    action: str,
    worker_id: str | None,
    reason: str,
    requested_by: str,
) -> dict[str, Any]:
    now = _now_utc()
    result: dict[str, Any] = {"status": "error", "action": action, "at": now.isoformat()}

    if action == "clear_control_queue":
        cleared = _clear_control_queue_requests(settings.state_dir, actor=requested_by)
        result = {
            "status": "ok",
            "action": action,
            "at": now.isoformat(),
            "cleared_requests": cleared,
            "message": f"Cleared {cleared} pending control request(s).",
        }
    elif action == "retry_failed":
        recent_workers = store.list_recent_workers(limit=250)
        target = _select_retry_target(recent_workers, requested_worker_id=worker_id)
        if target is None:
            result = {
                "status": "error",
                "action": action,
                "at": now.isoformat(),
                "message": "No failed worker available to retry.",
            }
        else:
            launch = await _launch_worker_from_record(app, target, reason=reason, requested_by=requested_by)
            if launch.get("status") == "ok":
                result = {
                    "status": "ok",
                    "action": action,
                    "at": now.isoformat(),
                    "worker_id": target.id,
                    "new_worker_id": launch.get("new_worker_id"),
                    "message": f"Retried failed worker {target.id}.",
                }
            else:
                result = {
                    "status": "error",
                    "action": action,
                    "at": now.isoformat(),
                    "worker_id": target.id,
                    "message": str(launch.get("message", "Retry failed")),
                }
    elif action == "restart_worker":
        if not worker_id:
            result = {
                "status": "error",
                "action": action,
                "at": now.isoformat(),
                "message": "worker_id is required for restart_worker.",
            }
        else:
            worker = store.get_worker(worker_id)
            if worker is None:
                result = {
                    "status": "error",
                    "action": action,
                    "at": now.isoformat(),
                    "message": f"Worker '{worker_id}' not found.",
                }
            else:
                stop_info = await _stop_worker_if_running(app, worker.id)
                launch = await _launch_worker_from_record(app, worker, reason=reason, requested_by=requested_by)
                if launch.get("status") == "ok":
                    result = {
                        "status": "ok",
                        "action": action,
                        "at": now.isoformat(),
                        "worker_id": worker.id,
                        "new_worker_id": launch.get("new_worker_id"),
                        "stopped": stop_info.get("stopped", False),
                        "message": f"Restarted worker {worker.id}.",
                    }
                else:
                    result = {
                        "status": "error",
                        "action": action,
                        "at": now.isoformat(),
                        "worker_id": worker.id,
                        "stopped": stop_info.get("stopped", False),
                        "message": str(launch.get("message", "Restart failed")),
                    }

    _append_dashboard_audit(
        store=store,
        action=action,
        result=result,
        requested_by=requested_by,
        worker_id=worker_id,
        reason=reason,
    )
    return result


def _append_dashboard_audit(
    *,
    store: SQLiteStore,
    action: str,
    result: dict[str, Any],
    requested_by: str,
    worker_id: str | None,
    reason: str,
) -> None:
    level = "info" if str(result.get("status")) == "ok" else "warning"
    store.append_audit(
        AuditEvent(
            id=f"dashboard-action-{uuid4().hex}",
            ts=_now_utc(),
            correlation_id=str(worker_id or ""),
            level=level,
            event_type="dashboard_action",
            data={
                "action": action,
                "requested_by": requested_by,
                "worker_id": worker_id,
                "reason": reason,
                "result": result,
            },
        )
    )


async def _stop_worker_if_running(app: FastAPI, worker_id: str) -> dict[str, Any]:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None or not hasattr(runtime, "stop_worker"):
        return {"stopped": False, "message": "Runtime unavailable"}
    try:
        stopped = bool(await runtime.stop_worker(worker_id))
    except Exception as exc:
        return {"stopped": False, "message": str(exc)}
    return {"stopped": stopped}


async def _launch_worker_from_record(
    app: FastAPI,
    worker: WorkerRecord,
    *,
    reason: str,
    requested_by: str,
) -> dict[str, Any]:
    queen = getattr(app.state, "queen", None)
    if queen is None or not hasattr(queen, "_start_worker_async"):
        return {"status": "error", "message": "Queen runtime is unavailable for worker launch."}
    template_id = str(worker.template_id or "").strip()
    if not template_id:
        return {"status": "error", "message": "Worker template_id missing; cannot restart/retry."}
    task = str(worker.task or "").strip()
    if not task:
        return {"status": "error", "message": "Worker task is empty; cannot restart/retry."}
    note = f"[dashboard:{requested_by}]"
    if reason:
        note += f" {reason}"
    launch = await queen._start_worker_async(
        worker_id=template_id,
        task=f"{task}\n\n{note}",
        chat_id=0,
        inputs={},
        tools=None,
        model=None,
        timeout_seconds=None,
    )
    new_worker_id = str(launch.get("worker_id", "")).strip() or None
    launch_status = str(launch.get("status", "")).strip().lower()
    if launch_status in {"started", "queued", "worker_started"} and new_worker_id:
        return {"status": "ok", "new_worker_id": new_worker_id, "launch": launch}
    if launch_status == "skipped_duplicate":
        return {"status": "error", "message": "Launch skipped as duplicate request."}
    return {"status": "error", "message": f"Launch failed with status={launch_status or 'unknown'}"}


def _select_retry_target(workers: list[WorkerRecord], requested_worker_id: str | None) -> WorkerRecord | None:
    if requested_worker_id:
        for worker in workers:
            if worker.id == requested_worker_id and str(worker.status).lower() == "failed":
                return worker
        return None
    for worker in workers:
        if str(worker.status).lower() == "failed":
            return worker
    return None


def _clear_control_queue_requests(state_dir: Path, *, actor: str) -> int:
    reqs = _read_jsonl(state_dir / "control_requests.jsonl")
    acks = _read_jsonl(state_dir / "control_acks.jsonl")
    acked_ids = {str(a.get("request_id", "")).strip() for a in acks}
    pending = [r for r in reqs if str(r.get("request_id", "")).strip() not in acked_ids]
    if not pending:
        return 0
    ack_file = state_dir / "control_acks.jsonl"
    count = 0
    for req in pending:
        request_id = str(req.get("request_id", "")).strip()
        if not request_id:
            continue
        item = {
            "request_id": request_id,
            "acked_at": _now_utc().isoformat(),
            "status": "cleared",
            "source": "dashboard_action",
            "actor": actor,
        }
        _append_jsonl(ack_file, item)
        count += 1
    return count


def _list_dashboard_action_history(store: SQLiteStore, limit: int = 15) -> list[dict[str, Any]]:
    events = store.list_audit(limit=max(limit * 5, 40))
    out: list[dict[str, Any]] = []
    for event in events:
        if event.event_type != "dashboard_action":
            continue
        data = event.data if isinstance(event.data, dict) else {}
        out.append(
            {
                "id": event.id,
                "timestamp": event.ts.isoformat(),
                "level": event.level,
                "action": data.get("action", ""),
                "requested_by": data.get("requested_by", ""),
                "worker_id": data.get("worker_id"),
                "reason": data.get("reason", ""),
                "result": data.get("result", {}),
            }
        )
        if len(out) >= limit:
            break
    return out


def _build_snapshot(settings: Settings, store: SQLiteStore, last: int, filters: DashboardFilters) -> dict[str, Any]:
    status_data = read_status(settings) or {}
    pid = status_data.get("pid")
    running = is_pid_running(pid)
    metrics = read_metrics_snapshot(settings.state_dir) or {}
    queen_metrics = metrics.get("queen", {}) if isinstance(metrics, dict) else {}
    telegram_metrics = metrics.get("telegram", {}) if isinstance(metrics, dict) else {}
    exec_metrics = metrics.get("exec_run", {}) if isinstance(metrics, dict) else {}
    connectivity_metrics = metrics.get("connectivity", {}) if isinstance(metrics, dict) else {}

    active_workers = store.get_active_workers(older_than_minutes=5)
    recent_workers = store.list_recent_workers(max(50, last))

    now = _now_utc()
    cutoff = now.timestamp() - 24 * 60 * 60
    spawned_24h = int(store.count_workers_created_since(datetime.fromtimestamp(cutoff, tz=UTC)))

    by_status: dict[str, int] = {}
    for worker in active_workers:
        by_status[worker.status] = by_status.get(worker.status, 0) + 1
    running_nodes = [w for w in active_workers if w.status in {"started", "running"}]
    root_running = sum(1 for w in running_nodes if not w.parent_worker_id)
    subworkers_running = sum(1 for w in running_nodes if bool(w.parent_worker_id))

    followup_q = int(queen_metrics.get("followup_queues", 0) or 0)
    internal_q = int(queen_metrics.get("internal_queues", 0) or 0)
    thinking_count = int(queen_metrics.get("thinking_count", 0) or 0)
    queen_state = "thinking" if thinking_count > 0 or (followup_q + internal_q) > 0 else "idle"

    requests = _read_jsonl(settings.state_dir / "control_requests.jsonl")
    acks = _read_jsonl(settings.state_dir / "control_acks.jsonl")
    acked_ids = {str(a.get("request_id", "")) for a in acks}
    pending_requests = [r for r in requests if str(r.get("request_id", "")) not in acked_ids]
    last_ack = acks[-1] if acks else None

    log_path = settings.state_dir / "logs" / "broodmind.log"
    incident_logs = _collect_logs(log_path, max_lines=600, filters=filters)
    recent_logs = _tail_logs(log_path, 12, filters=filters)
    log_health = _compute_log_health(log_path, now, window_minutes=filters.window_minutes, filters=filters)
    latency_p95_ms = _estimate_control_latency_p95_ms(requests, acks)
    queue_depth = followup_q + internal_q + int(telegram_metrics.get("chat_queues", 0) or 0) + len(pending_requests)
    active_workers_kpi = by_status.get("running", 0) + by_status.get("started", 0)
    mcp_servers = connectivity_metrics.get("mcp_servers", {})

    services_all = _build_service_health(
        now=now,
        system_running=running,
        system_last_heartbeat=status_data.get("last_message_at"),
        queen_metrics=queen_metrics,
        telegram_metrics=telegram_metrics,
        exec_metrics=exec_metrics,
        mcp_servers=mcp_servers if isinstance(mcp_servers, dict) else {},
    )
    services = [s for s in services_all if _service_matches_filter(str(s.get("id", "all")), filters.service)]
    if not services:
        services = services_all
    overall_status, overall_reasons = _derive_overall_health(
        services=services_all,
        failed_workers=by_status.get("failed", 0),
        control_pending=len(pending_requests),
        log_health=log_health,
        system_running=running,
    )
    kpis = _build_kpis(
        latency_p95_ms=latency_p95_ms,
        log_health=log_health,
        queue_depth=queue_depth,
        active_workers=active_workers_kpi,
    )
    incidents = _build_incidents(
        services=services_all,
        recent_workers=recent_workers,
        logs=incident_logs,
        control_pending=len(pending_requests),
        queue_depth=queue_depth,
    )
    slo = _build_slo_metrics(
        services=services_all,
        log_health=log_health,
        recent_workers=recent_workers,
    )
    noise_control = _build_noise_control(logs=incident_logs)

    return {
        "contract_version": "dashboard.v1",
        "generated_at": now.isoformat(),
        "filters": _filters_payload(filters, settings),
        "health": {
            "status": overall_status,
            "summary": _health_summary(overall_status, overall_reasons),
            "reasons": overall_reasons,
        },
        "kpis": kpis,
        "services": services,
        "incidents": incidents,
        "slo": slo,
        "noise_control": noise_control,
        "system": {
            "running": running,
            "pid": pid,
            "active_channel": status_data.get("active_channel", "Telegram"),
            "started_at": status_data.get("started_at"),
            "last_heartbeat": status_data.get("last_message_at"),
            "uptime": _uptime_human(status_data.get("started_at")),
        },
        "queen": {
            "state": queen_state,
            "followup_queues": followup_q,
            "internal_queues": internal_q,
            "followup_tasks": int(queen_metrics.get("followup_tasks", 0) or 0),
            "internal_tasks": int(queen_metrics.get("internal_tasks", 0) or 0),
        },
        "connectivity": {"mcp_servers": mcp_servers if isinstance(mcp_servers, dict) else {}},
        "logs": recent_logs,
        "queues": {
            "telegram_send_tasks": int(telegram_metrics.get("send_tasks", 0) or 0),
            "telegram_queues": int(telegram_metrics.get("chat_queues", 0) or 0),
            "exec_sessions_running": int(exec_metrics.get("background_sessions_running", 0) or 0),
            "exec_sessions_total": int(exec_metrics.get("background_sessions_total", 0) or 0),
        },
        "workers": {
            "spawned_24h": spawned_24h,
            "running": by_status.get("running", 0) + by_status.get("started", 0),
            "root_running": root_running,
            "subworkers_running": subworkers_running,
            "completed": by_status.get("completed", 0),
            "failed": by_status.get("failed", 0),
            "stopped": by_status.get("stopped", 0),
            "topology": [
                {
                    "id": w.id,
                    "template_name": w.template_name or w.template_id or "",
                    "status": w.status,
                    "task": w.task,
                    "updated_at": w.updated_at.isoformat(),
                    "parent_worker_id": w.parent_worker_id,
                    "lineage_id": w.lineage_id,
                    "spawn_depth": w.spawn_depth,
                }
                for w in running_nodes
            ],
            "recent": [
                {
                    "id": w.id,
                    "template_name": w.template_name or w.template_id or "",
                    "status": w.status,
                    "task": w.task,
                    "updated_at": w.updated_at.isoformat(),
                    "summary": w.summary or "",
                    "error": w.error or "",
                    "tools_used": w.tools_used or [],
                    "parent_worker_id": w.parent_worker_id,
                    "lineage_id": w.lineage_id,
                    "spawn_depth": w.spawn_depth,
                }
                for w in recent_workers[:last]
            ],
        },
        "control": {
            "pending_requests": len(pending_requests),
            "last_ack": last_ack,
        },
        "actions": {
            "history": _list_dashboard_action_history(store, limit=8),
        },
    }


def _build_kpis(
    *,
    latency_p95_ms: int | None,
    log_health: dict[str, Any],
    queue_depth: int,
    active_workers: int,
) -> dict[str, Any]:
    error_rate = float(log_health.get("error_rate_5m", 0.0) or 0.0)
    latency_status = "unknown"
    if latency_p95_ms is not None:
        if latency_p95_ms >= 5000:
            latency_status = "critical"
        elif latency_p95_ms >= 2000:
            latency_status = "warning"
        else:
            latency_status = "ok"

    error_status = "ok"
    if error_rate >= 0.5:
        error_status = "critical"
    elif error_rate >= 0.2:
        error_status = "warning"

    queue_status = "ok"
    if queue_depth >= 30:
        queue_status = "critical"
    elif queue_depth >= 10:
        queue_status = "warning"

    worker_status = "ok" if active_workers > 0 else "warning"
    return {
        "latency_ms_p95": {"value": latency_p95_ms, "unit": "ms", "status": latency_status},
        "error_rate_5m": {"value": round(error_rate * 100, 1), "unit": "%", "status": error_status},
        "queue_depth": {"value": int(queue_depth), "unit": "count", "status": queue_status},
        "active_workers": {"value": int(active_workers), "unit": "count", "status": worker_status},
        "error_count_5m": int(log_health.get("error_count_5m", 0) or 0),
        "event_count_5m": int(log_health.get("event_count_5m", 0) or 0),
    }


def _build_service_health(
    *,
    now: datetime,
    system_running: bool,
    system_last_heartbeat: str | None,
    queen_metrics: dict[str, Any],
    telegram_metrics: dict[str, Any],
    exec_metrics: dict[str, Any],
    mcp_servers: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    heartbeat_age = _age_seconds(system_last_heartbeat, now)
    gateway_status = "ok" if system_running else "critical"
    gateway_reason = "running" if system_running else "process is not running"
    if system_running and heartbeat_age is not None and heartbeat_age > 300:
        gateway_status = "warning"
        gateway_reason = f"heartbeat stale for {int(heartbeat_age)}s"
    out.append(
        {
            "id": "gateway",
            "name": "Gateway",
            "status": gateway_status,
            "reason": gateway_reason,
            "updated_at": system_last_heartbeat,
        }
    )

    followup_q = int(queen_metrics.get("followup_queues", 0) or 0)
    internal_q = int(queen_metrics.get("internal_queues", 0) or 0)
    thinking_count = int(queen_metrics.get("thinking_count", 0) or 0)
    queen_queue_pressure = followup_q + internal_q
    queen_status = "ok"
    queen_reason = "idle"
    if queen_queue_pressure >= 20:
        queen_status = "critical"
        queen_reason = f"queue pressure high ({queen_queue_pressure})"
    elif queen_queue_pressure >= 8:
        queen_status = "warning"
        queen_reason = f"queue pressure rising ({queen_queue_pressure})"
    elif thinking_count > 0:
        queen_reason = "processing tasks"
    out.append(
        {
            "id": "queen",
            "name": "Queen",
            "status": queen_status,
            "reason": queen_reason,
            "updated_at": queen_metrics.get("updated_at"),
            "metrics": {
                "followup_queues": followup_q,
                "internal_queues": internal_q,
                "thinking_count": thinking_count,
            },
        }
    )

    telegram_q = int(telegram_metrics.get("chat_queues", 0) or 0)
    telegram_status = "ok"
    telegram_reason = "healthy"
    telegram_age = _age_seconds(str(telegram_metrics.get("updated_at", "")), now)
    if telegram_q >= 40:
        telegram_status = "critical"
        telegram_reason = f"chat queues overloaded ({telegram_q})"
    elif telegram_q >= 15:
        telegram_status = "warning"
        telegram_reason = f"chat queues elevated ({telegram_q})"
    elif telegram_age is not None and telegram_age > 240:
        telegram_status = "warning"
        telegram_reason = f"metrics stale for {int(telegram_age)}s"
    out.append(
        {
            "id": "telegram",
            "name": "Telegram",
            "status": telegram_status,
            "reason": telegram_reason,
            "updated_at": telegram_metrics.get("updated_at"),
            "metrics": {"chat_queues": telegram_q, "send_tasks": int(telegram_metrics.get("send_tasks", 0) or 0)},
        }
    )

    sessions_running = int(exec_metrics.get("background_sessions_running", 0) or 0)
    exec_status = "ok"
    exec_reason = "idle"
    if sessions_running >= 24:
        exec_status = "critical"
        exec_reason = f"many background sessions ({sessions_running})"
    elif sessions_running >= 8:
        exec_status = "warning"
        exec_reason = f"background sessions elevated ({sessions_running})"
    elif sessions_running > 0:
        exec_reason = f"{sessions_running} session(s) running"
    out.append(
        {
            "id": "exec_run",
            "name": "Exec Run",
            "status": exec_status,
            "reason": exec_reason,
            "updated_at": exec_metrics.get("updated_at"),
            "metrics": {"background_sessions_running": sessions_running},
        }
    )

    mcp_error = 0
    mcp_warn = 0
    for payload in mcp_servers.values():
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("status", "unknown")).lower()
        if status == "error":
            mcp_error += 1
        elif status != "connected":
            mcp_warn += 1
    mcp_total = len(mcp_servers)
    mcp_status = "ok"
    mcp_reason = "no MCP servers configured" if mcp_total == 0 else f"{mcp_total} server(s) connected"
    if mcp_error > 0:
        mcp_status = "critical"
        mcp_reason = f"{mcp_error} MCP server(s) in error"
    elif mcp_warn > 0:
        mcp_status = "warning"
        mcp_reason = f"{mcp_warn} MCP server(s) not connected"
    out.append(
        {
            "id": "mcp",
            "name": "MCP",
            "status": mcp_status,
            "reason": mcp_reason,
            "updated_at": None,
            "metrics": {"total": mcp_total, "error": mcp_error, "warning": mcp_warn},
        }
    )
    return out


def _derive_overall_health(
    *,
    services: list[dict[str, Any]],
    failed_workers: int,
    control_pending: int,
    log_health: dict[str, Any],
    system_running: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    severity = "ok"

    def _raise(level: str) -> None:
        nonlocal severity
        rank = {"ok": 0, "warning": 1, "critical": 2}
        if rank[level] > rank[severity]:
            severity = level

    for service in services:
        status = str(service.get("status", "ok"))
        if status in {"warning", "critical"}:
            _raise(status)
            reasons.append(f"{service.get('name', service.get('id', 'service'))}: {service.get('reason', status)}")

    if not system_running:
        _raise("critical")
        reasons.append("System process is not running")

    if failed_workers >= 5:
        _raise("critical")
        reasons.append(f"{failed_workers} failed workers active")
    elif failed_workers > 0:
        _raise("warning")
        reasons.append(f"{failed_workers} failed worker(s)")

    if control_pending >= 10:
        _raise("warning")
        reasons.append(f"{control_pending} pending control requests")

    error_rate = float(log_health.get("error_rate_5m", 0.0) or 0.0)
    event_count = int(log_health.get("event_count_5m", 0) or 0)
    if event_count >= 5 and error_rate >= 0.5:
        _raise("critical")
        reasons.append("High log error rate in last 5 minutes")
    elif event_count >= 5 and error_rate >= 0.2:
        _raise("warning")
        reasons.append("Elevated log error rate in last 5 minutes")

    return severity, reasons[:6]


def _health_summary(status: str, reasons: list[str]) -> str:
    label = status.upper()
    if not reasons:
        return f"{label}: all systems normal"
    return f"{label}: {reasons[0]}"


def _build_incidents(
    *,
    services: list[dict[str, Any]],
    recent_workers: list[WorkerRecord],
    logs: list[dict[str, Any]],
    control_pending: int,
    queue_depth: int,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for service in services:
        status = str(service.get("status", "ok")).lower()
        if status not in {"warning", "critical"}:
            continue
        severity = "critical" if status == "critical" else "warning"
        impact = 90 if severity == "critical" else 60
        items.append(
            {
                "id": f"svc-{service.get('id', 'service')}",
                "service": str(service.get("id", "gateway")),
                "severity": severity,
                "impact": impact,
                "title": f"{service.get('name', service.get('id', 'Service'))} health {severity}",
                "summary": str(service.get("reason", "")),
                "count": 1,
                "latest_at": str(service.get("updated_at", "")),
                "source": "service_health",
            }
        )

    failed_workers = [w for w in recent_workers if str(w.status).lower() == "failed"]
    if failed_workers:
        worker_count = len(failed_workers)
        sev = "critical" if worker_count >= 3 else "warning"
        sample_ids = ", ".join(w.id[:8] for w in failed_workers[:3])
        items.append(
            {
                "id": "workers-failed",
                "service": "workers",
                "severity": sev,
                "impact": 70 + min(20, worker_count * 5),
                "title": "Worker failures",
                "summary": f"{worker_count} failed worker(s): {sample_ids}",
                "count": worker_count,
                "latest_at": failed_workers[0].updated_at.isoformat(),
                "source": "worker_status",
            }
        )

    log_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for log in logs:
        level = str(log.get("level", "info")).lower()
        if level not in {"warning", "error", "critical"}:
            continue
        severity = "critical" if level in {"error", "critical"} else "warning"
        service = str(log.get("service", "gateway"))
        category = _categorize_incident_event(str(log.get("event", "")))
        key = (service, category, severity)
        group = log_groups.get(key)
        if group is None:
            group = {
                "id": f"log-{service}-{category}-{severity}",
                "service": service,
                "severity": severity,
                "impact": 84 if severity == "critical" else 55,
                "title": f"{service} {category}",
                "summary": str(log.get("event", ""))[:140],
                "count": 0,
                "latest_at": str(log.get("timestamp", "")),
                "source": "logs",
            }
            log_groups[key] = group
        group["count"] = int(group.get("count", 0)) + 1
        ts = str(log.get("timestamp", ""))
        if ts and ts > str(group.get("latest_at", "")):
            group["latest_at"] = ts
    for group in log_groups.values():
        count = int(group.get("count", 0))
        if count < 2 and str(group.get("severity")) != "critical":
            continue
        group["impact"] = int(group.get("impact", 50)) + min(15, count * 2)
        group["summary"] = f"{group['summary']} ({count} events)"
        items.append(group)

    if control_pending >= 8:
        items.append(
            {
                "id": "control-queue-backlog",
                "service": "gateway",
                "severity": "warning",
                "impact": 62 + min(15, control_pending),
                "title": "Control queue backlog",
                "summary": f"{control_pending} pending control requests",
                "count": control_pending,
                "latest_at": "",
                "source": "control_queue",
            }
        )

    if queue_depth >= 20:
        items.append(
            {
                "id": "queue-depth-pressure",
                "service": "queen",
                "severity": "warning",
                "impact": 65 + min(20, queue_depth // 2),
                "title": "Queue pressure",
                "summary": f"Queue depth is {queue_depth}",
                "count": queue_depth,
                "latest_at": "",
                "source": "queues",
            }
        )

    items.sort(
        key=lambda x: (
            _severity_rank(str(x.get("severity", "warning"))),
            int(x.get("impact", 0)),
            int(x.get("count", 0)),
        ),
        reverse=True,
    )
    top_items = items[:5]
    critical = sum(1 for i in top_items if str(i.get("severity")) == "critical")
    warning = sum(1 for i in top_items if str(i.get("severity")) == "warning")
    return {
        "summary": {"open": len(top_items), "critical": critical, "warning": warning},
        "items": top_items,
    }


def _build_slo_metrics(
    *,
    services: list[dict[str, Any]],
    log_health: dict[str, Any],
    recent_workers: list[WorkerRecord],
) -> dict[str, Any]:
    availability_target = 99.0
    error_budget_target = 1.0
    error_budget_fraction = error_budget_target / 100.0

    core_services = [s for s in services if str(s.get("id", "")) in {"gateway", "queen", "telegram", "exec_run"}]
    if not core_services:
        uptime_pct = 100.0
    else:
        points = 0.0
        for service in core_services:
            status = str(service.get("status", "ok")).lower()
            if status == "ok":
                points += 1.0
            elif status == "warning":
                points += 0.6
            else:
                points += 0.0
        uptime_pct = round((points / len(core_services)) * 100.0, 1)

    error_rate_fraction = float(log_health.get("error_rate_5m", 0.0) or 0.0)
    burn_rate = round(error_rate_fraction / max(error_budget_fraction, 1e-6), 2)
    error_budget_remaining_pct = round(max(0.0, 100.0 - (burn_rate * 10.0)), 1)

    mttr_minutes = _estimate_mttr_minutes(recent_workers)
    uptime_status = "ok" if uptime_pct >= availability_target else ("warning" if uptime_pct >= 95.0 else "critical")
    burn_status = "ok" if burn_rate <= 1.0 else ("warning" if burn_rate <= 2.0 else "critical")
    if mttr_minutes is None:
        mttr_status = "warning"
    elif mttr_minutes <= 15:
        mttr_status = "ok"
    elif mttr_minutes <= 45:
        mttr_status = "warning"
    else:
        mttr_status = "critical"

    return {
        "objectives": {"availability_target_pct": availability_target, "error_budget_pct": error_budget_target},
        "uptime_pct": {"value": uptime_pct, "status": uptime_status},
        "burn_rate": {"value": burn_rate, "status": burn_status},
        "error_budget_remaining_pct": {"value": error_budget_remaining_pct, "status": burn_status},
        "mttr_minutes": {"value": mttr_minutes, "status": mttr_status},
    }


def _estimate_mttr_minutes(recent_workers: list[WorkerRecord]) -> float | None:
    failed = [w for w in recent_workers if str(w.status).lower() == "failed"]
    if not failed:
        return 0.0
    completed = [w for w in recent_workers if str(w.status).lower() == "completed"]
    durations: list[float] = []
    for f in failed[:10]:
        candidate: WorkerRecord | None = None
        for c in completed:
            if c.updated_at <= f.updated_at:
                continue
            same_template = bool(f.template_id and c.template_id and f.template_id == c.template_id)
            if same_template or not f.template_id:
                if candidate is None or c.updated_at < candidate.updated_at:
                    candidate = c
        if candidate is None:
            continue
        delta_min = (candidate.updated_at - f.updated_at).total_seconds() / 60.0
        if delta_min >= 0:
            durations.append(delta_min)
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def _build_noise_control(*, logs: list[dict[str, Any]]) -> dict[str, Any]:
    noisy = [l for l in logs if str(l.get("level", "")).lower() in {"warning", "error", "critical"}]
    raw_alerts = len(noisy)
    groups: dict[tuple[str, str, str], int] = {}
    for log in noisy:
        service = str(log.get("service", "gateway"))
        severity = "critical" if str(log.get("level", "")).lower() in {"error", "critical"} else "warning"
        category = _categorize_incident_event(str(log.get("event", "")))
        key = (service, category, severity)
        groups[key] = groups.get(key, 0) + 1
    deduped_alerts = len(groups)
    suppressed = max(0, raw_alerts - deduped_alerts)
    reduction_pct = round((suppressed / raw_alerts) * 100.0, 1) if raw_alerts > 0 else 0.0
    top_groups = sorted(groups.items(), key=lambda kv: kv[1], reverse=True)[:4]
    top = [
        {"service": s, "category": c, "severity": sev, "count": count}
        for (s, c, sev), count in top_groups
    ]
    return {
        "raw_alerts": raw_alerts,
        "deduped_alerts": deduped_alerts,
        "suppressed_alerts": suppressed,
        "reduction_pct": reduction_pct,
        "top_groups": top,
    }


def _categorize_incident_event(event: str) -> str:
    text = event.lower()
    if "timeout" in text:
        return "timeouts"
    if "auth" in text or "unauthorized" in text:
        return "auth"
    if "queue" in text or "backlog" in text:
        return "queue"
    if "connection" in text or "socket" in text:
        return "connectivity"
    if "worker" in text and ("failed" in text or "error" in text):
        return "worker_failures"
    if "rate" in text and "limit" in text:
        return "rate_limits"
    return "errors"


def _severity_rank(severity: str) -> int:
    s = severity.strip().lower()
    if s == "critical":
        return 2
    if s == "warning":
        return 1
    return 0


def _compute_log_health(
    log_path: Path,
    now: datetime,
    window_minutes: int = 5,
    *,
    filters: DashboardFilters | None = None,
) -> dict[str, Any]:
    cutoff = now.timestamp() - window_minutes * 60
    total = 0
    errors = 0
    effective_filters = filters or DashboardFilters(window_minutes=window_minutes, service="all", environment="all")
    for data in _collect_logs(log_path, max_lines=1000, filters=effective_filters):
        ts = _parse_timestamp(str(data.get("timestamp", "")))
        if ts is not None and ts.timestamp() < cutoff:
            continue
        total += 1
        level = str(data.get("level", "info")).lower()
        if level in {"error", "critical"}:
            errors += 1
    return {
        "window_minutes": window_minutes,
        "event_count_5m": total,
        "error_count_5m": errors,
        "error_rate_5m": (errors / total) if total > 0 else 0.0,
    }


def _estimate_control_latency_p95_ms(requests: list[dict[str, Any]], acks: list[dict[str, Any]]) -> int | None:
    if not requests or not acks:
        return None
    by_request_id: dict[str, datetime] = {}
    for req in requests:
        rid = str(req.get("request_id", "")).strip()
        if not rid:
            continue
        ts = _extract_event_timestamp(req)
        if ts is not None:
            by_request_id[rid] = ts

    samples_ms: list[int] = []
    for ack in acks:
        rid = str(ack.get("request_id", "")).strip()
        if not rid:
            continue
        req_ts = by_request_id.get(rid)
        ack_ts = _extract_event_timestamp(ack)
        if req_ts is None or ack_ts is None:
            continue
        delta_ms = int((ack_ts - req_ts).total_seconds() * 1000)
        if 0 <= delta_ms <= 30 * 60 * 1000:
            samples_ms.append(delta_ms)
    if not samples_ms:
        return None
    samples_ms.sort()
    idx = int(math.ceil(0.95 * len(samples_ms))) - 1
    idx = max(0, min(idx, len(samples_ms) - 1))
    return samples_ms[idx]


def _extract_event_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "created_at", "requested_at", "acked_at", "updated_at"):
        raw = payload.get(key)
        if raw is None:
            continue
        ts = _parse_timestamp(str(raw))
        if ts is not None:
            return ts
    return None


def _parse_timestamp(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_seconds(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    dt = _parse_timestamp(str(value))
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds())


def _service_matches_filter(service: str, selected: str) -> bool:
    if selected == "all":
        return True
    return service.strip().lower() == selected.strip().lower()


def _detect_log_service(payload: dict[str, Any], event: str) -> str:
    candidates = [
        str(payload.get("service", "")),
        str(payload.get("component", "")),
        str(payload.get("module", "")),
        str(payload.get("logger", "")),
    ]
    haystack = " ".join(candidates + [event]).lower()
    if "telegram" in haystack:
        return "telegram"
    if "queen" in haystack:
        return "queen"
    if "exec_run" in haystack or "exec run" in haystack:
        return "exec_run"
    if "mcp" in haystack:
        return "mcp"
    if "worker" in haystack:
        return "workers"
    if "gateway" in haystack or "websocket" in haystack or "fastapi" in haystack:
        return "gateway"
    return "gateway"


def _extract_log_environment(payload: dict[str, Any]) -> str:
    for key in ("environment", "env", "stage"):
        raw = str(payload.get(key, "")).strip().lower()
        if raw:
            cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
            if cleaned:
                return cleaned
    return "local"


def _tail_logs(path: Path, max_lines: int, *, filters: DashboardFilters) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for data in _collect_logs(path, max_lines=1000, filters=filters):
        out.append(
            {
                "event": str(data.get("event", ""))[:120],
                "level": str(data.get("level", "info")),
                "timestamp": str(data.get("timestamp", "")),
                "service": str(data.get("service", "unknown")),
            }
        )
        if len(out) >= max_lines:
            break
    return out


def _collect_logs(path: Path, max_lines: int, *, filters: DashboardFilters) -> list[dict[str, Any]]:
    now = _now_utc()
    cutoff = now.timestamp() - max(1, filters.window_minutes) * 60
    out: list[dict[str, Any]] = []
    for line in _read_last_lines(path, max_lines=max_lines):
        entry = _normalize_log_entry(line, filters=filters)
        if entry is None:
            continue
        ts = _parse_timestamp(str(entry.get("timestamp", "")))
        if ts is not None and ts.timestamp() < cutoff:
            continue
        out.append(entry)
    out.reverse()
    return out


def _normalize_log_entry(line: str, *, filters: DashboardFilters) -> dict[str, Any] | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        service = _detect_log_service({}, raw)
        if not _service_matches_filter(service, filters.service):
            return None
        environment = "local"
        if filters.environment != "all" and filters.environment != environment:
            return None
        return {"event": raw[:200], "level": "info", "timestamp": "", "service": service, "environment": environment}
    if not isinstance(parsed, dict):
        return None
    event = str(parsed.get("event", ""))[:200]
    level = str(parsed.get("level", "info"))
    timestamp = str(parsed.get("timestamp", ""))
    service = _detect_log_service(parsed, event)
    environment = _extract_log_environment(parsed)
    if not _service_matches_filter(service, filters.service):
        return None
    if filters.environment != "all" and filters.environment != environment:
        return None
    return {
        "event": event,
        "level": level,
        "timestamp": timestamp,
        "service": service,
        "environment": environment,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in _read_last_lines(path, max_lines=250):
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_last_lines(path: Path, max_lines: int = 200, max_bytes: int = 256 * 1024) -> list[str]:
    if not path.exists() or max_lines <= 0:
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    start = max(0, size - max(1, max_bytes))
    tail: deque[str] = deque(maxlen=max_lines)
    try:
        with path.open("rb") as handle:
            if start > 0:
                handle.seek(start)
                _ = handle.readline()
            for raw in handle:
                text = raw.decode("utf-8", errors="ignore").rstrip("\n\r")
                tail.append(text)
    except OSError:
        return []
    return list(tail)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _uptime_human(started_at: str | None) -> str:
    if not started_at:
        return "N/A"
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return "N/A"
    delta = _now_utc() - start
    total = int(delta.total_seconds())
    if total < 0:
        return "N/A"
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BroodMind Control Deck</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --ink: #e5e7eb;
      --muted: #98a4b8;
      --paper: #0a0f1b;
      --panel: rgba(16, 24, 43, 0.78);
      --line: #25324d;
      --teal: #2dd4bf;
      --amber: #f59e0b;
      --rose: #fb7185;
      --mint: #34d399;
      --sky: #38bdf8;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      color: var(--ink);
      font-family: "Space Grotesk", sans-serif;
      background:
        radial-gradient(1000px 600px at 5% -5%, rgba(56, 189, 248, 0.18), transparent 60%),
        radial-gradient(900px 700px at 100% 0%, rgba(251, 113, 133, 0.14), transparent 55%),
        linear-gradient(170deg, #070b14, #0a1220 48%, #0b1526);
    }
    .noise::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.06;
      background-image: radial-gradient(#fff 0.4px, transparent 0.5px);
      background-size: 3px 3px;
    }
    .wrap { width: min(1280px, 96vw); margin: 24px auto 40px; }
    .topbar {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .headline { display: flex; gap: 12px; align-items: baseline; }
    .title {
      margin: 0;
      font-size: clamp(24px, 3.4vw, 38px);
      line-height: 1;
      letter-spacing: 0.02em;
    }
    .subtitle { color: var(--muted); font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; }
    .controls { display: flex; gap: 8px; flex-wrap: wrap; }
    .input, .btn {
      border: 1px solid var(--line);
      background: rgba(7, 13, 23, 0.85);
      color: var(--ink);
      border-radius: 12px;
      height: 40px;
      padding: 0 12px;
      font-family: inherit;
    }
    .input { width: 260px; }
    .filter-select { width: 146px; }
    .btn {
      cursor: pointer;
      font-weight: 600;
      transition: transform 120ms ease, border-color 120ms ease, background-color 120ms ease;
    }
    .btn:hover { transform: translateY(-1px); border-color: var(--sky); }
    .btn.primary { background: linear-gradient(90deg, #0f766e, #155e75); border-color: transparent; }
    .status-strip {
      display: grid;
      grid-template-columns: repeat(5, minmax(160px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .kpi {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
      transform: translateY(8px);
      opacity: 0;
      animation: lift 420ms ease forwards;
    }
    .kpi:nth-child(2) { animation-delay: 80ms; }
    .kpi:nth-child(3) { animation-delay: 120ms; }
    .kpi:nth-child(4) { animation-delay: 180ms; }
    .kpi:nth-child(5) { animation-delay: 240ms; }
    .kpi-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }
    .kpi-value { margin-top: 6px; font-size: 28px; font-weight: 700; line-height: 1.1; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      padding: 3px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }
    .ok { color: var(--mint); }
    .warn { color: var(--amber); }
    .bad { color: var(--rose); }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
      gap: 10px;
    }
    .services-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(180px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .service {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px;
      background: rgba(9, 15, 28, 0.72);
    }
    .service-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
    }
    .service-name {
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .service-status {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .service-reason {
      font-size: 13px;
      line-height: 1.35;
      min-height: 2.4em;
    }
    .service-updated {
      margin-top: 6px;
      font-size: 11px;
      color: var(--muted);
      font-family: "JetBrains Mono", monospace;
    }
    .drilldown-btn {
      margin-top: 8px;
      width: 100%;
      height: 30px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: rgba(16, 24, 43, 0.9);
      color: var(--ink);
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
    }
    .drilldown-btn:hover {
      border-color: var(--sky);
      transform: translateY(-1px);
    }
    .actions-grid {
      display: grid;
      grid-template-columns: 1.3fr 1fr;
      gap: 10px;
      margin-bottom: 10px;
    }
    .actions-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }
    .input.worker-id { width: 220px; }
    .btn.warn { background: linear-gradient(90deg, #7c2d12, #9a3412); border-color: transparent; }
    .btn.danger { background: linear-gradient(90deg, #7f1d1d, #b91c1c); border-color: transparent; }
    .action-history {
      max-height: 180px;
      overflow: auto;
      display: grid;
      gap: 6px;
    }
    .action-item {
      border: 1px solid rgba(37, 50, 77, 0.75);
      border-radius: 10px;
      padding: 8px;
      background: rgba(9, 15, 28, 0.75);
      font-size: 12px;
      line-height: 1.35;
    }
    .incidents-grid {
      display: grid;
      gap: 8px;
      margin-bottom: 10px;
    }
    .incident-item {
      border: 1px solid rgba(37, 50, 77, 0.75);
      border-radius: 12px;
      padding: 10px;
      background: rgba(9, 15, 28, 0.78);
    }
    .incident-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      margin-bottom: 6px;
    }
    .incident-title { font-size: 14px; font-weight: 700; margin-bottom: 3px; }
    .incident-meta {
      font-size: 11px;
      color: var(--muted);
      font-family: "JetBrains Mono", monospace;
      margin-top: 5px;
    }
    .slo-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }
    .slo-item {
      border: 1px solid rgba(37, 50, 77, 0.75);
      border-radius: 12px;
      padding: 10px;
      background: rgba(9, 15, 28, 0.78);
    }
    .slo-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .slo-value { margin-top: 6px; font-size: 22px; font-weight: 700; }
    .slo-hint { margin-top: 4px; font-size: 11px; color: var(--muted); }
    .mobile-only { display: none; }
    .mobile-oncall {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(9, 15, 28, 0.82);
      padding: 12px;
      margin-bottom: 10px;
    }
    .mobile-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }
    .mobile-title { font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
    .mobile-health { font-size: 20px; font-weight: 700; }
    .mobile-incidents { display: grid; gap: 6px; margin-bottom: 8px; }
    .mobile-incident {
      border: 1px solid rgba(37, 50, 77, 0.75);
      border-radius: 10px;
      padding: 8px;
      font-size: 12px;
      background: rgba(11, 18, 31, 0.85);
    }
    .mobile-actions { display: grid; gap: 8px; }
    .mobile-actions .btn { width: 100%; }
    .layout > * { min-width: 0; }
    .layout.mcp-topology {
      grid-template-columns: minmax(220px, 320px) minmax(0, 1fr);
      align-items: start;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.2);
      overflow: hidden;
    }
    .card h3 { margin: 0 0 10px; font-size: 15px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }
    .chart-wrap { height: 230px; }
    .skeleton-wrap { display: grid; gap: 8px; }
    .skeleton-line {
      height: 12px;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(37, 50, 77, 0.35), rgba(56, 189, 248, 0.26), rgba(37, 50, 77, 0.35));
      background-size: 200% 100%;
      animation: shimmer 1.2s ease-in-out infinite;
    }
    .skeleton-line.sm { width: 34%; }
    .skeleton-line.md { width: 62%; }
    .skeleton-line.lg { width: 88%; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 9px 6px; border-bottom: 1px solid rgba(37, 50, 77, 0.75); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    td strong { font-size: 12px; }
    .mono { font-family: "JetBrains Mono", monospace; }
    .task-prefix { color: var(--amber); font-weight: 700; }
    .task-prefix-sched { color: var(--mint); font-weight: 700; }
    .workers { max-height: 310px; overflow: auto; }
    .logs { max-height: 270px; overflow: auto; }
    .log-line { border-bottom: 1px dashed rgba(37, 50, 77, 0.75); padding: 8px 2px; font-size: 13px; line-height: 1.35; }
    .topology { max-height: 190px; overflow: auto; display: grid; gap: 8px; }
    .topo-row {
      border: 1px solid rgba(37, 50, 77, 0.75);
      border-radius: 12px;
      padding: 8px 10px;
      background: rgba(9, 15, 28, 0.75);
    }
    .topo-head { display: flex; gap: 8px; align-items: center; justify-content: space-between; font-size: 12px; }
    .topo-id { font-family: "JetBrains Mono", monospace; color: #c7d2fe; }
    .topo-task {
      margin-top: 6px;
      font-size: 12px;
      color: var(--ink);
      white-space: normal;
      word-break: break-word;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .topo-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 2px 8px;
      border: 1px solid var(--line);
      font-size: 11px;
      color: var(--muted);
    }
    .pulse {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--mint);
      box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.8);
      animation: pulse 1.4s infinite;
    }
    .meta { margin-top: 10px; color: var(--muted); font-size: 12px; font-family: "JetBrains Mono", monospace; }
    .err { color: var(--rose); margin-top: 8px; font-size: 13px; min-height: 1.1em; }
    .workers table { table-layout: fixed; }
    .workers th:nth-child(1), .workers td:nth-child(1) { width: 14%; }
    .workers th:nth-child(2), .workers td:nth-child(2) { width: 8%; }
    .workers th:nth-child(3), .workers td:nth-child(3) { width: 46%; word-break: break-word; }
    .workers th:nth-child(4), .workers td:nth-child(4) { width: 12%; }
    .workers th:nth-child(5), .workers td:nth-child(5) { width: 20%; word-break: break-word; }
    @keyframes lift { to { transform: translateY(0); opacity: 1; } }
    @keyframes shimmer {
      0% { background-position: 180% 0; }
      100% { background-position: -40% 0; }
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.8); }
      70% { box-shadow: 0 0 0 8px rgba(52, 211, 153, 0); }
      100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
    }
    @media (max-width: 1060px) {
      .status-strip { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
      .services-grid { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
      .layout { grid-template-columns: 1fr; }
      .actions-grid { grid-template-columns: 1fr; }
      .slo-grid { grid-template-columns: repeat(2, minmax(130px, 1fr)); }
    }
    @media (max-width: 580px) {
      .wrap { width: min(1280px, 94vw); }
      .controls { width: 100%; }
      .input { width: 100%; }
      .filter-select { width: 100%; }
      .btn { flex: 1; }
      .status-strip { grid-template-columns: 1fr; }
      .services-grid { grid-template-columns: 1fr; }
      .slo-grid { grid-template-columns: 1fr; }
      .desktop-heavy { display: none; }
      .mobile-only { display: block; }
    }
  </style>
</head>
<body class="noise">
  <div class="wrap">
    <div class="topbar">
      <div class="headline">
        <h1 class="title">BroodMind Control Deck</h1>
        <span class="subtitle">private tailnet telemetry</span>
      </div>
      <div class="controls">
        <input id="token" class="input" type="password" placeholder="Dashboard token" />
        <select id="filter-window" class="input filter-select">
          <option value="15">15m</option>
          <option value="60" selected>1h</option>
          <option value="240">4h</option>
          <option value="1440">24h</option>
        </select>
        <select id="filter-service" class="input filter-select">
          <option value="all" selected>All services</option>
          <option value="gateway">Gateway</option>
          <option value="queen">Queen</option>
          <option value="telegram">Telegram</option>
          <option value="exec_run">Exec Run</option>
          <option value="mcp">MCP</option>
          <option value="workers">Workers</option>
        </select>
        <select id="filter-env" class="input filter-select">
          <option value="all" selected>All envs</option>
          <option value="local">local</option>
          <option value="dev">dev</option>
          <option value="staging">staging</option>
          <option value="prod">prod</option>
        </select>
        <button id="save-token" class="btn">Save Token</button>
        <button id="refresh" class="btn primary">Refresh</button>
      </div>
    </div>

    <section class="status-strip">
      <article class="kpi">
        <div class="kpi-label">Overall Health</div>
        <div id="health-status" class="kpi-value">-</div>
        <div id="chip-health" class="chip">No summary</div>
      </article>
      <article class="kpi">
        <div class="kpi-label">Latency p95</div>
        <div id="kpi-latency" class="kpi-value">-</div>
        <div id="chip-latency" class="chip">Control ack latency</div>
      </article>
      <article class="kpi">
        <div class="kpi-label">Error Rate</div>
        <div id="kpi-error-rate" class="kpi-value">0%</div>
        <div id="chip-errors" class="chip">errors - / events - (window)</div>
      </article>
      <article class="kpi">
        <div class="kpi-label">Queue Depth</div>
        <div id="kpi-queue-depth" class="kpi-value">0</div>
        <div id="chip-queues" class="chip">followup - | internal - | telegram -</div>
      </article>
      <article class="kpi">
        <div class="kpi-label">Active Workers</div>
        <div id="kpi-active-workers" class="kpi-value">0</div>
        <div id="chip-workers" class="chip">failed - | completed -</div>
      </article>
    </section>

    <section class="mobile-only">
      <div class="mobile-oncall">
        <div class="mobile-head">
          <div class="mobile-title">On-Call View</div>
          <div id="mobile-health" class="mobile-health">-</div>
        </div>
        <div id="mobile-summary" class="meta">No summary yet.</div>
        <div id="mobile-incidents" class="mobile-incidents"><div class="meta">No incidents.</div></div>
        <div class="mobile-actions">
          <button id="mobile-retry-failed-btn" class="btn">Retry Latest Failed</button>
          <button id="mobile-clear-queue-btn" class="btn danger">Clear Control Queue</button>
        </div>
      </div>
    </section>

    <section class="card" style="margin-bottom: 10px;">
      <h3>Service Health</h3>
      <div id="services-grid" class="services-grid">No service data yet.</div>
    </section>

    <section class="card" style="margin-bottom: 10px;">
      <h3>Incidents</h3>
      <div id="incident-summary" class="meta">No incidents.</div>
      <div id="incidents-list" class="incidents-grid"><div class="meta">No incidents.</div></div>
    </section>

    <section class="card" style="margin-bottom: 10px;">
      <h3>SLO / SLA</h3>
      <div id="slo-targets" class="meta">targets: n/a</div>
      <div class="slo-grid">
        <article class="slo-item">
          <div class="slo-label">Uptime</div>
          <div id="slo-uptime" class="slo-value">-</div>
          <div id="slo-uptime-hint" class="slo-hint">-</div>
        </article>
        <article class="slo-item">
          <div class="slo-label">Burn Rate</div>
          <div id="slo-burn" class="slo-value">-</div>
          <div id="slo-burn-hint" class="slo-hint">-</div>
        </article>
        <article class="slo-item">
          <div class="slo-label">Error Budget Left</div>
          <div id="slo-budget" class="slo-value">-</div>
          <div id="slo-budget-hint" class="slo-hint">-</div>
        </article>
        <article class="slo-item">
          <div class="slo-label">MTTR</div>
          <div id="slo-mttr" class="slo-value">-</div>
          <div id="slo-mttr-hint" class="slo-hint">-</div>
        </article>
      </div>
      <div id="noise-summary" class="meta">noise control: n/a</div>
    </section>

    <section class="actions-grid">
      <article class="card">
        <h3>Quick Actions</h3>
        <div class="actions-row" style="margin-bottom: 8px;">
          <input id="restart-worker-id" class="input worker-id" type="text" placeholder="Worker ID to restart" />
          <button id="restart-worker-btn" class="btn warn">Restart Worker</button>
          <button id="retry-failed-btn" class="btn">Retry Latest Failed</button>
          <button id="clear-queue-btn" class="btn danger">Clear Control Queue</button>
        </div>
        <div class="meta" id="action-result">No actions yet.</div>
      </article>
      <article class="card">
        <h3>Action History</h3>
        <div id="action-history" class="action-history"><div class="meta">No actions yet.</div></div>
      </article>
    </section>

    <section class="layout desktop-heavy">
      <div class="card">
        <h3>Worker Throughput (rolling)</h3>
        <div class="chart-wrap"><canvas id="activity-chart"></canvas></div>
      </div>
      <div class="card">
        <h3>Recent Events</h3>
        <div id="logs" class="logs">
          <div class="skeleton-wrap">
            <div class="skeleton-line sm"></div>
            <div class="skeleton-line lg"></div>
            <div class="skeleton-line md"></div>
            <div class="skeleton-line lg"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="layout mcp-topology desktop-heavy" style="margin-top: 10px;">
      <div class="card">
        <h3>MCP Connectivity</h3>
        <div id="mcp-status">
          <div class="skeleton-wrap">
            <div class="skeleton-line md"></div>
            <div class="skeleton-line lg"></div>
            <div class="skeleton-line sm"></div>
          </div>
        </div>
      </div>
      <div class="card">
        <h3>Live Worker Topology</h3>
        <div id="worker-topology" class="topology">
          <div class="skeleton-wrap">
            <div class="skeleton-line lg"></div>
            <div class="skeleton-line md"></div>
            <div class="skeleton-line lg"></div>
          </div>
        </div>
      </div>
    </section>

    <section class="card desktop-heavy" style="margin-top: 10px;">
      <h3>Recent Workers</h3>
      <div class="workers">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Task</th>
              <th>Last Tool</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody id="workers-table">
            <tr><td colspan="5"><div class="skeleton-wrap"><div class="skeleton-line lg"></div><div class="skeleton-line md"></div><div class="skeleton-line lg"></div></div></td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="meta" id="meta">Last refresh: never</div>
    <div class="err" id="error"></div>
  </div>

  <script>
    const tokenInput = document.getElementById("token");
    const filterWindowInput = document.getElementById("filter-window");
    const filterServiceInput = document.getElementById("filter-service");
    const filterEnvInput = document.getElementById("filter-env");
    const saveBtn = document.getElementById("save-token");
    const refreshBtn = document.getElementById("refresh");
    const servicesGridEl = document.getElementById("services-grid");
    const restartWorkerInput = document.getElementById("restart-worker-id");
    const restartWorkerBtn = document.getElementById("restart-worker-btn");
    const retryFailedBtn = document.getElementById("retry-failed-btn");
    const clearQueueBtn = document.getElementById("clear-queue-btn");
    const actionResultEl = document.getElementById("action-result");
    const actionHistoryEl = document.getElementById("action-history");
    const incidentsListEl = document.getElementById("incidents-list");
    const mobileHealthEl = document.getElementById("mobile-health");
    const mobileSummaryEl = document.getElementById("mobile-summary");
    const mobileIncidentsEl = document.getElementById("mobile-incidents");
    const mobileRetryFailedBtn = document.getElementById("mobile-retry-failed-btn");
    const mobileClearQueueBtn = document.getElementById("mobile-clear-queue-btn");
    const tokenKey = "broodmind.dashboard.token";
    const filterKey = "broodmind.dashboard.filters";
    tokenInput.value = localStorage.getItem(tokenKey) || "";
    const savedFilters = (() => {
      try {
        return JSON.parse(localStorage.getItem(filterKey) || "{}");
      } catch (_err) {
        return {};
      }
    })();
    filterWindowInput.value = String(savedFilters.window_minutes || filterWindowInput.value || "60");
    filterServiceInput.value = String(savedFilters.service || filterServiceInput.value || "all");
    filterEnvInput.value = String(savedFilters.environment || filterEnvInput.value || "all");

    const historySize = 30;
    const history = [];
    let chart = null;
    let refreshTick = 0;
    let hasSuccessfulLoad = false;
    const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
    const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
      timeZone: browserTimeZone
    });
    const timeFormatter = new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
      timeZone: browserTimeZone
    });

    saveBtn.addEventListener("click", () => {
      localStorage.setItem(tokenKey, tokenInput.value || "");
      runOnce();
    });
    refreshBtn.addEventListener("click", runOnce);
    filterWindowInput.addEventListener("change", () => { persistFilters(); runOnce(); });
    filterServiceInput.addEventListener("change", () => { persistFilters(); runOnce(); });
    filterEnvInput.addEventListener("change", () => { persistFilters(); runOnce(); });
    servicesGridEl.addEventListener("click", (event) => {
      const target = event.target;
      const button = target && target.closest ? target.closest("[data-drill-service]") : null;
      if (!button) return;
      const service = String(button.getAttribute("data-drill-service") || "all");
      filterServiceInput.value = service;
      persistFilters();
      runOnce(true);
    });
    incidentsListEl.addEventListener("click", (event) => {
      const target = event.target;
      const button = target && target.closest ? target.closest("[data-incident-service]") : null;
      if (!button) return;
      const service = String(button.getAttribute("data-incident-service") || "all");
      filterServiceInput.value = service;
      persistFilters();
      runOnce(true);
    });
    restartWorkerBtn.addEventListener("click", async () => {
      const workerId = String(restartWorkerInput.value || "").trim();
      if (!workerId) {
        actionResultEl.textContent = "Enter a worker ID first.";
        return;
      }
      const ok = window.confirm("Restart worker " + workerId + "? This will stop and relaunch the worker.");
      if (!ok) return;
      await runAction("restart_worker", { worker_id: workerId, confirm: true });
    });
    retryFailedBtn.addEventListener("click", async () => {
      await runAction("retry_failed", {});
    });
    clearQueueBtn.addEventListener("click", async () => {
      const ok = window.confirm("Clear all pending control requests?");
      if (!ok) return;
      await runAction("clear_control_queue", { confirm: true });
    });
    mobileRetryFailedBtn.addEventListener("click", async () => {
      await runAction("retry_failed", {});
    });
    mobileClearQueueBtn.addEventListener("click", async () => {
      const ok = window.confirm("Clear all pending control requests?");
      if (!ok) return;
      await runAction("clear_control_queue", { confirm: true });
    });

    function headers() {
      const token = tokenInput.value || "";
      return token ? { "x-broodmind-token": token } : {};
    }

    function currentFilters() {
      return {
        window_minutes: Number(filterWindowInput.value || 60),
        service: String(filterServiceInput.value || "all"),
        environment: String(filterEnvInput.value || "all")
      };
    }

    function persistFilters() {
      localStorage.setItem(filterKey, JSON.stringify(currentFilters()));
    }

    function filtersToQuery(filters) {
      const params = new URLSearchParams();
      params.set("window_minutes", String(filters.window_minutes || 60));
      params.set("service", String(filters.service || "all"));
      params.set("environment", String(filters.environment || "all"));
      return params.toString();
    }

    function esc(v) {
      return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    }

    function statusClass(value) {
      const v = String(value || "").toLowerCase();
      if (["running", "idle", "thinking", "connected", "ok", "completed"].includes(v)) return "ok";
      if (["warning", "stopped"].includes(v)) return "warn";
      return "bad";
    }

    function kpiStatusClass(status) {
      const s = String(status || "").toLowerCase();
      if (s === "ok") return "ok";
      if (s === "warning") return "warn";
      return "bad";
    }

    function highlightTaskPrefixes(text) {
      const source = String(text || "");
      const parts = source.split(/(\\[[^\\]]+\\])/g);
      return parts.map((part) => {
        if (!part) return "";
        if (part.startsWith("[") && part.endsWith("]")) {
          const cls = part.toLowerCase().includes("schedul") ? "task-prefix-sched" : "task-prefix";
          return "<span class='" + cls + "'>" + esc(part) + "</span>";
        }
        return esc(part);
      }).join("");
    }

    function setKpi(id, text, cls) {
      const el = document.getElementById(id);
      el.textContent = text;
      el.className = "kpi-value " + (cls || "");
    }

    function setChip(id, text) {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = text;
    }

    function formatKpiValue(kpi, fallback) {
      if (!kpi || kpi.value === null || kpi.value === undefined) return fallback;
      const value = kpi.value;
      const unit = String(kpi.unit || "");
      if (unit === "%") return String(value) + "%";
      if (unit === "ms") return String(value) + " ms";
      return String(value);
    }

    function formatTimestampLocal(value) {
      if (value === null || value === undefined || value === "") return "never";
      const raw = String(value).trim();
      const d = value instanceof Date ? value : new Date(raw);
      if (Number.isNaN(d.getTime())) return raw;
      return dateTimeFormatter.format(d);
    }

    function formatTimeLocal(value) {
      if (value === null || value === undefined || value === "") return "never";
      const d = value instanceof Date ? value : new Date(String(value).trim());
      if (Number.isNaN(d.getTime())) return String(value);
      return timeFormatter.format(d);
    }

    function applyFilterOptions(filtersPayload) {
      if (!filtersPayload || !filtersPayload.options) return;
      const options = filtersPayload.options;
      const setSelectOptions = (selectEl, values) => {
        if (!selectEl || !Array.isArray(values) || !values.length) return;
        const selected = String(selectEl.value || "");
        const html = values.map((value) => "<option value='" + esc(value) + "'>" + esc(value) + "</option>");
        selectEl.innerHTML = html.join("");
        if (values.map(String).includes(selected)) {
          selectEl.value = selected;
        }
      };
      setSelectOptions(filterWindowInput, options.window_minutes);
      setSelectOptions(filterServiceInput, options.service);
      setSelectOptions(filterEnvInput, options.environment);
      if (typeof filtersPayload.window_minutes !== "undefined") {
        filterWindowInput.value = String(filtersPayload.window_minutes);
      }
      if (typeof filtersPayload.service !== "undefined") {
        filterServiceInput.value = String(filtersPayload.service);
      }
      if (typeof filtersPayload.environment !== "undefined") {
        filterEnvInput.value = String(filtersPayload.environment);
      }
    }

    function ensureChart() {
      if (chart) return chart;
      const ctx = document.getElementById("activity-chart");
      chart = new Chart(ctx, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "Running workers",
              data: [],
              borderColor: "#34d399",
              backgroundColor: "rgba(52, 211, 153, 0.20)",
              fill: true,
              tension: 0.3,
              pointRadius: 0
            },
            {
              label: "Queue pressure",
              data: [],
              borderColor: "#f59e0b",
              backgroundColor: "rgba(245, 158, 11, 0.14)",
              fill: true,
              tension: 0.3,
              pointRadius: 0
            }
          ]
        },
        options: {
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: "#98a4b8", boxWidth: 12 } }
          },
          scales: {
            x: { ticks: { color: "#98a4b8", maxTicksLimit: 6 }, grid: { color: "rgba(37, 50, 77, 0.42)" } },
            y: { ticks: { color: "#98a4b8" }, grid: { color: "rgba(37, 50, 77, 0.42)" }, beginAtZero: true }
          }
        }
      });
      return chart;
    }

    function updateChartPoint(data) {
      const queuePressure = Number(data.queen.followup_queues || 0) + Number(data.queen.internal_queues || 0);
      history.push({
        t: formatTimeLocal(new Date()),
        workers: Number(data.workers.running || 0),
        queues: queuePressure
      });
      while (history.length > historySize) history.shift();
      const c = ensureChart();
      c.data.labels = history.map((h) => h.t);
      c.data.datasets[0].data = history.map((h) => h.workers);
      c.data.datasets[1].data = history.map((h) => h.queues);
      const peak = Math.max(
        0,
        ...history.map((h) => Math.max(Number(h.workers || 0), Number(h.queues || 0)))
      );
      const paddedMax = peak <= 2 ? 4 : Math.max(4, Math.ceil(peak * 1.35));
      c.options.scales.y.max = paddedMax;
      c.options.scales.y.suggestedMax = paddedMax;
      c.update();
    }

    function renderWorkers(workers) {
      const rows = (workers || []).map((w) => {
        const lastTool = (Array.isArray(w.tools_used) && w.tools_used.length > 0) ? w.tools_used[w.tools_used.length - 1] : "-";
        const taskRaw = String(w.task || "");
        const taskShort = taskRaw.length > 220 ? (taskRaw.slice(0, 217) + "...") : taskRaw;
        const fullId = String(w.id || "");
        const shortId = fullId.includes("-") ? fullId.split("-")[0] : fullId.slice(0, 8);
        const workerName = String(w.template_name || "").trim();
        const workerDisplay = workerName ? (workerName + " (" + shortId + ")") : shortId;
        return "<tr>" +
          "<td class='mono' title='" + esc(fullId) + "'>" + esc(workerDisplay) + "</td>" +
          "<td class='" + statusClass(w.status) + "'><strong>" + esc(w.status) + "</strong></td>" +
          "<td title='" + esc(taskRaw) + "'>" + highlightTaskPrefixes(taskShort) + "</td>" +
          "<td class='mono'>" + esc(lastTool) + "</td>" +
          "<td class='mono'>" + esc(formatTimestampLocal(w.updated_at)) + "</td>" +
          "</tr>";
      });
      document.getElementById("workers-table").innerHTML = rows.length ? rows.join("") : "<tr><td colspan='5'>No workers</td></tr>";
    }

    function renderWorkersIfNeeded(workers, force) {
      const shouldRender = force || !hasSuccessfulLoad || (refreshTick % 2 === 0);
      if (shouldRender) renderWorkers(workers);
    }

    function renderLogs(logs) {
      const el = document.getElementById("logs");
      const html = (logs || []).map((l) => {
        const level = String(l.level || "info").toLowerCase();
        const cls = level === "error" ? "bad" : (level === "warning" ? "warn" : "ok");
        const service = String(l.service || "gateway");
        const when = l.timestamp ? formatTimeLocal(l.timestamp) : "-";
        return "<div class='log-line'>" +
          "<span class='" + cls + "'>" + esc(level.toUpperCase()) + "</span> " +
          "<span class='mono'>" + esc(when) + "</span> " +
          "<span class='mono'>[" + esc(service) + "]</span> " +
          esc(l.event || "") +
          "</div>";
      });
      el.innerHTML = html.length ? html.join("") : "No logs.";
      el.scrollTop = el.scrollHeight;
    }

    function renderMcp(servers) {
      const mcp = servers || {};
      const keys = Object.keys(mcp);
      if (!keys.length) {
        document.getElementById("mcp-status").innerHTML = "<div class='meta'>No MCP servers configured.</div>";
        return;
      }
      const rows = keys.map((k) => {
        const item = mcp[k] || {};
        const name = item.name || k;
        const status = String(item.status || "unknown").toLowerCase();
        const toolCount = Number(item.tool_count || 0);
        const cls = status === "connected" ? "ok" : (status === "error" ? "bad" : "warn");
        return "<div class='log-line'>" +
          "<strong>" + esc(name) + "</strong> " +
          "<span class='" + cls + "'>" + esc(status.toUpperCase()) + "</span> " +
          "<span class='mono'>(" + toolCount + " tools)</span>" +
          "</div>";
      });
      document.getElementById("mcp-status").innerHTML = rows.join("");
    }

    function renderMcpIfNeeded(servers, force) {
      const shouldRender = force || !hasSuccessfulLoad || (refreshTick % 5 === 0);
      if (shouldRender) renderMcp(servers);
    }

    function renderTopology(nodes) {
      const items = Array.isArray(nodes) ? nodes.slice() : [];
      items.sort((a, b) => {
        const depthA = Number(a.spawn_depth || 0);
        const depthB = Number(b.spawn_depth || 0);
        if (depthA !== depthB) return depthA - depthB;
        return String(a.updated_at || "").localeCompare(String(b.updated_at || ""));
      });
      if (!items.length) {
        document.getElementById("worker-topology").innerHTML = "No running workers.";
        return;
      }
      const html = items.map((w) => {
        const depth = Math.max(0, Number(w.spawn_depth || 0));
        const left = Math.min(depth * 16, 64);
        const parent = w.parent_worker_id ? ("child of " + String(w.parent_worker_id).slice(0, 8)) : "root worker";
        const wid = String(w.id || "");
        const shortId = wid.includes("-") ? wid.split("-")[0] : wid.slice(0, 8);
        const workerName = String(w.template_name || "").trim();
        const workerLabel = workerName ? (workerName + " (" + shortId + ")") : shortId;
        return "<div class='topo-row' style='margin-left:" + left + "px'>" +
          "<div class='topo-head'>" +
          "<span class='topo-id' title='" + esc(wid) + "'>" + esc(workerLabel) + "</span>" +
          "<span class='topo-badge'><span class='pulse'></span>" + esc(parent) + "</span>" +
          "</div>" +
          "<div class='topo-task'>" + highlightTaskPrefixes(w.task || "") + "</div>" +
          "</div>";
      });
      document.getElementById("worker-topology").innerHTML = html.join("");
    }

    function renderTopologyIfNeeded(nodes, force) {
      const shouldRender = force || !hasSuccessfulLoad || (refreshTick % 2 === 0);
      if (shouldRender) renderTopology(nodes);
    }

    function renderServices(services) {
      const list = Array.isArray(services) ? services : [];
      if (!list.length) {
        document.getElementById("services-grid").innerHTML = "<div class='meta'>No service data yet.</div>";
        return;
      }
      const html = list.map((service) => {
        const status = String(service.status || "unknown").toLowerCase();
        const cls = status === "ok" ? "ok" : (status === "warning" ? "warn" : "bad");
        const updated = service.updated_at ? formatTimestampLocal(service.updated_at) : "n/a";
        return "<article class='service'>" +
          "<div class='service-head'>" +
          "<span class='service-name'>" + esc(service.name || service.id || "service") + "</span>" +
          "<span class='service-status " + cls + "'>" + esc(status) + "</span>" +
          "</div>" +
          "<div class='service-reason'>" + esc(service.reason || "-") + "</div>" +
          "<div class='service-updated'>updated " + esc(updated) + "</div>" +
          "<button class='drilldown-btn' data-drill-service='" + esc(service.id || "all") + "'>View Logs</button>" +
          "</article>";
      });
      document.getElementById("services-grid").innerHTML = html.join("");
    }

    async function fetchFilteredLogs(filters, lines = 80) {
      const query = filtersToQuery(filters) + "&lines=" + String(lines);
      const rsp = await fetch("/api/dashboard/logs?" + query, { headers: headers() });
      if (!rsp.ok) throw new Error("LOG API " + rsp.status);
      return await rsp.json();
    }

    async function runAction(action, payload) {
      try {
        const body = {
          action: action,
          reason: "triggered from dashboard",
          requested_by: "dashboard",
          ...payload
        };
        const rsp = await fetch("/api/dashboard/actions", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers() },
          body: JSON.stringify(body)
        });
        if (!rsp.ok) {
          const text = await rsp.text();
          throw new Error("ACTION API " + rsp.status + " " + text);
        }
        const data = await rsp.json();
        actionResultEl.textContent = String(data.message || (data.status + ": " + action));
      } catch (err) {
        actionResultEl.textContent = "Action failed: " + String(err);
      }
      await runOnce(false);
    }

    function renderActionHistory(entries) {
      const list = Array.isArray(entries) ? entries : [];
      if (!list.length) {
        actionHistoryEl.innerHTML = "<div class='meta'>No actions yet.</div>";
        return;
      }
      const html = list.map((entry) => {
        const status = String((entry.result || {}).status || "unknown");
        const cls = status === "ok" ? "ok" : "warn";
        const at = formatTimestampLocal(entry.timestamp);
        const workerId = entry.worker_id ? (" | worker " + entry.worker_id) : "";
        const message = String((entry.result || {}).message || "");
        return "<div class='action-item'>" +
          "<div><span class='" + cls + "'>" + esc(status.toUpperCase()) + "</span> " + esc(entry.action || "") + workerId + "</div>" +
          "<div class='mono'>" + esc(at) + " by " + esc(entry.requested_by || "dashboard") + "</div>" +
          "<div>" + esc(message || "-") + "</div>" +
          "</div>";
      });
      actionHistoryEl.innerHTML = html.join("");
    }

    function renderIncidents(incidents) {
      const payload = incidents || {};
      const summary = payload.summary || {};
      const items = Array.isArray(payload.items) ? payload.items : [];
      const summaryText =
        "Open " + String(summary.open || 0) +
        " | critical " + String(summary.critical || 0) +
        " | warning " + String(summary.warning || 0);
      document.getElementById("incident-summary").textContent = summaryText;
      if (!items.length) {
        incidentsListEl.innerHTML = "<div class='meta'>No active incidents in selected window.</div>";
        return;
      }
      const html = items.map((item) => {
        const sev = String(item.severity || "warning").toLowerCase();
        const cls = sev === "critical" ? "bad" : "warn";
        const latest = item.latest_at ? formatTimestampLocal(item.latest_at) : "n/a";
        return "<article class='incident-item'>" +
          "<div class='incident-head'>" +
          "<span class='" + cls + "'>" + esc(sev.toUpperCase()) + "</span>" +
          "<span class='mono'>impact " + esc(item.impact || 0) + "</span>" +
          "</div>" +
          "<div class='incident-title'>" + esc(item.title || "Incident") + "</div>" +
          "<div>" + esc(item.summary || "-") + "</div>" +
          "<div class='incident-meta'>service=" + esc(item.service || "gateway") +
          " | count=" + esc(item.count || 0) +
          " | latest=" + esc(latest) + "</div>" +
          "<button class='drilldown-btn' data-incident-service='" + esc(item.service || "all") + "'>View Logs</button>" +
          "</article>";
      });
      incidentsListEl.innerHTML = html.join("");
    }

    function renderMobileOnCall(health, incidents) {
      const h = health || {};
      const status = String(h.status || "unknown").toUpperCase();
      mobileHealthEl.textContent = status;
      mobileHealthEl.className = "mobile-health " + kpiStatusClass(h.status);
      mobileSummaryEl.textContent = String(h.summary || "No summary.");

      const items = Array.isArray((incidents || {}).items) ? incidents.items : [];
      if (!items.length) {
        mobileIncidentsEl.innerHTML = "<div class='meta'>No active incidents.</div>";
        return;
      }
      const top = items.slice(0, 3);
      const html = top.map((item) => {
        const sev = String(item.severity || "warning");
        const cls = sev === "critical" ? "bad" : "warn";
        return "<div class='mobile-incident'>" +
          "<span class='" + cls + "'>" + esc(sev.toUpperCase()) + "</span> " +
          "<strong>" + esc(item.title || "Incident") + "</strong><br/>" +
          esc(item.summary || "-") +
          "</div>";
      });
      mobileIncidentsEl.innerHTML = html.join("");
    }

    function renderSlo(slo, noise) {
      const payload = slo || {};
      const objectives = payload.objectives || {};
      const uptime = payload.uptime_pct || {};
      const burn = payload.burn_rate || {};
      const budget = payload.error_budget_remaining_pct || {};
      const mttr = payload.mttr_minutes || {};
      const fmt = (value, suffix, fallback = "n/a") => {
        if (value === null || value === undefined) return fallback;
        return String(value) + suffix;
      };
      const setSlo = (id, value, status) => {
        const el = document.getElementById(id);
        el.textContent = value;
        el.className = "slo-value " + kpiStatusClass(status);
      };
      setSlo("slo-uptime", fmt(uptime.value, "%"), uptime.status);
      setSlo("slo-burn", fmt(burn.value, "x"), burn.status);
      setSlo("slo-budget", fmt(budget.value, "%"), burn.status);
      setSlo("slo-mttr", mttr.value === null || mttr.value === undefined ? "n/a" : fmt(mttr.value, "m"), mttr.status);

      document.getElementById("slo-targets").textContent =
        "targets: availability " + String(objectives.availability_target_pct || 99) +
        "% | error budget " + String(objectives.error_budget_pct || 1) + "%";
      document.getElementById("slo-uptime-hint").textContent = "service availability score";
      document.getElementById("slo-burn-hint").textContent = "consumption rate vs budget";
      document.getElementById("slo-budget-hint").textContent = "estimated remaining budget";
      document.getElementById("slo-mttr-hint").textContent = "mean time to recovery";

      const n = noise || {};
      const top = Array.isArray(n.top_groups) ? n.top_groups : [];
      const topText = top.length
        ? top.map((g) => g.service + ":" + g.category + " x" + g.count).join(" | ")
        : "no noisy groups";
      document.getElementById("noise-summary").textContent =
        "noise control: raw " + String(n.raw_alerts || 0) +
        " -> dedup " + String(n.deduped_alerts || 0) +
        " | reduced " + String(n.reduction_pct || 0) + "%" +
        " | top " + topText;
    }

    async function runOnce(focusLogs = false) {
      const errorEl = document.getElementById("error");
      errorEl.textContent = "";
      const startedAt = performance.now();
      try {
        const filters = currentFilters();
        const query = "last=14&" + filtersToQuery(filters);
        const rsp = await fetch("/api/dashboard/snapshot?" + query, { headers: headers() });
        if (!rsp.ok) throw new Error("API " + rsp.status);
        const data = await rsp.json();
        const health = data.health || {};
        const kpis = data.kpis || {};
        const filterPayload = data.filters || filters;

        setKpi("health-status", String(health.status || "unknown").toUpperCase(), kpiStatusClass(health.status));
        setKpi("kpi-latency", formatKpiValue(kpis.latency_ms_p95, "n/a"), kpiStatusClass((kpis.latency_ms_p95 || {}).status));
        setKpi("kpi-error-rate", formatKpiValue(kpis.error_rate_5m, "0%"), kpiStatusClass((kpis.error_rate_5m || {}).status));
        setKpi("kpi-queue-depth", formatKpiValue(kpis.queue_depth, "0"), kpiStatusClass((kpis.queue_depth || {}).status));
        setKpi("kpi-active-workers", formatKpiValue(kpis.active_workers, "0"), kpiStatusClass((kpis.active_workers || {}).status));

        setChip("chip-health", String(health.summary || "No summary"));
        setChip("chip-latency", "channel " + String(data.system.active_channel || "-") + " | uptime " + String(data.system.uptime || "N/A"));
        setChip(
          "chip-errors",
          "errors " + String(kpis.error_count_5m || 0) +
          " / events " + String(kpis.event_count_5m || 0) +
          " (" + String(currentFilters().window_minutes) + "m)"
        );
        setChip(
          "chip-queues",
          "followup " + String(data.queen.followup_queues || 0) +
          " | internal " + String(data.queen.internal_queues || 0) +
          " | telegram " + String(data.queues.telegram_queues || 0)
        );
        setChip("chip-workers", "failed " + String(data.workers.failed || 0) + " | completed " + String(data.workers.completed || 0));

        applyFilterOptions(filterPayload);
        persistFilters();

        renderWorkersIfNeeded(data.workers.recent || [], focusLogs);
        renderServices(data.services || []);
        renderIncidents(data.incidents || {});
        renderMobileOnCall(data.health || {}, data.incidents || {});
        renderSlo(data.slo || {}, data.noise_control || {});
        renderActionHistory((data.actions || {}).history || []);
        renderMcpIfNeeded((data.connectivity || {}).mcp_servers || {}, focusLogs);
        renderTopologyIfNeeded(data.workers.topology || [], focusLogs);
        updateChartPoint(data);
        try {
          const shouldRefreshLogs = focusLogs || !hasSuccessfulLoad || (refreshTick % 3 === 0);
          if (shouldRefreshLogs) {
            const logsRsp = await fetchFilteredLogs(currentFilters(), focusLogs ? 140 : 80);
            renderLogs(logsRsp.entries || []);
          }
        } catch (logErr) {
          renderLogs(data.logs || []);
          console.error(logErr);
        }

        const renderMs = Math.round(performance.now() - startedAt);
        const nowTick = refreshTick;
        refreshTick += 1;
        hasSuccessfulLoad = true;
        document.getElementById("meta").textContent =
          "Last refresh " + formatTimestampLocal(new Date()) +
          " | heartbeat " + formatTimestampLocal(data.system.last_heartbeat) +
          " | window " + String(currentFilters().window_minutes) + "m" +
          " | service " + String(currentFilters().service) +
          " | env " + String(currentFilters().environment) +
          " | render " + String(renderMs) + "ms" +
          " | tick " + String(nowTick) +
          " | tz " + (browserTimeZone || "local") +
          " | pid " + (data.system.pid || "N/A");
        if (focusLogs) {
          document.getElementById("logs").scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (err) {
        errorEl.textContent = "Dashboard request failed: " + err;
      }
    }

    runOnce();
    setInterval(runOnce, 2000);
  </script>
</body>
</html>
"""
