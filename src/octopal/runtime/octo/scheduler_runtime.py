from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from typing import Any

import structlog

from octopal.infrastructure.observability.base import now_ms
from octopal.infrastructure.observability.helpers import (
    safe_preview,
    summarize_exception,
)
from octopal.runtime.metrics import update_component_gauges
from octopal.runtime.octo import followup_delivery as _followup_delivery
from octopal.runtime.octo.background_tracing import (
    _finish_background_trace_context,
    _start_background_trace_context,
)
from octopal.runtime.octo.control_plane import RouteMode
from octopal.runtime.octo.control_replies import _has_scheduler_idle_suffix
from octopal.runtime.octo.delivery import DeliveryMode, resolve_user_delivery
from octopal.runtime.octo.router import (
    normalize_plain_text,
)
from octopal.runtime.octo.router import (
    route_proactive_tick as _default_route_proactive_tick,
)
from octopal.runtime.octo.router import (
    route_scheduler_tick as _default_route_scheduler_tick,
)
from octopal.runtime.octo.runtime_config import _env_flag, _env_int
from octopal.runtime.octo.scheduler_helpers import _empty_scheduler_metric_counters
from octopal.runtime.state import update_last_scheduler_tick as _default_update_last_scheduler_tick
from octopal.utils import (
    extract_heartbeat_user_visible_message,
    has_no_user_response_suffix,
    utc_now,
)

logger = structlog.get_logger(__name__)

_default_send_scheduler_control_update = _followup_delivery._send_scheduler_control_update
_DEFAULT_PROACTIVE_TICK_ENABLED = _env_flag("OCTOPAL_PROACTIVE_TICK_ENABLED", True)
_DEFAULT_PROACTIVE_TICK_MIN_INTERVAL_SECONDS = float(
    _env_int("OCTOPAL_PROACTIVE_TICK_MIN_INTERVAL_SECONDS", 21600, minimum=0)
)


def _core_callable(name: str, default: Callable[..., Any]) -> Callable[..., Any]:
    core_module = sys.modules.get("octopal.runtime.octo.core")
    if core_module is not None:
        candidate = getattr(core_module, name, None)
        if callable(candidate):
            return candidate
    return default


def _core_value(name: str, default: Any) -> Any:
    core_module = sys.modules.get("octopal.runtime.octo.core")
    if core_module is not None and hasattr(core_module, name):
        return getattr(core_module, name)
    return default


class OctoSchedulerRuntimeMixin:
    def _publish_scheduler_metrics(
        self,
        *,
        running: bool,
        interval_seconds: int | None = None,
        max_tasks: int | None = None,
        last_tick_status: str | None = None,
        due_count: int | None = None,
        result_preview: str | None = None,
        dispatch_summary: dict[str, int] | None = None,
    ) -> None:
        counters = self._scheduler_metric_counters or _empty_scheduler_metric_counters()
        payload: dict[str, Any] = {
            "running": bool(running),
            "configured": self.scheduler is not None,
            **counters,
        }
        resolved_interval = interval_seconds
        if resolved_interval is None:
            resolved_interval = self._scheduler_interval_seconds
        resolved_max_tasks = max_tasks
        if resolved_max_tasks is None:
            resolved_max_tasks = self._scheduler_max_tasks
        if resolved_interval is not None:
            payload["interval_seconds"] = int(resolved_interval)
        if resolved_max_tasks is not None:
            payload["max_tasks"] = int(resolved_max_tasks)
        if last_tick_status is not None:
            payload["last_tick_status"] = str(last_tick_status)
        if due_count is not None:
            payload["last_due_count"] = int(due_count)
        if result_preview is not None:
            payload["last_result_preview"] = str(result_preview)
        if dispatch_summary is not None:
            payload["last_dispatch_attempted"] = int(dispatch_summary.get("attempted") or 0)
            payload["last_dispatch_started"] = int(dispatch_summary.get("started") or 0)
            payload["last_dispatch_completed"] = int(dispatch_summary.get("completed") or 0)
            payload["last_dispatch_duplicates"] = int(dispatch_summary.get("duplicates") or 0)
            payload["last_dispatch_rejected_by_policy"] = int(
                dispatch_summary.get("rejected_by_policy") or 0
            )
            payload["last_dispatch_errors"] = int(dispatch_summary.get("errors") or 0)
            payload["last_policy_reasons"] = dict(dispatch_summary.get("policy_reasons") or {})
        update_component_gauges("scheduler", payload)

    async def _run_scheduler_tick_once(self, *, chat_id: int = 0, max_tasks: int = 10) -> None:
        if self.scheduler is None:
            return
        trace_started_at_ms = now_ms()
        trace_metadata: dict[str, Any] = {
            "route_mode": RouteMode.SCHEDULER.value,
            "chat_id": chat_id,
            "dry_run": False,
            "max_tasks": max_tasks,
        }
        trace_ctx, trace_token, is_root_trace = await _start_background_trace_context(
            self.trace_sink,
            name="octo.scheduler_tick",
            chat_id=chat_id,
            correlation_id=None,
            metadata=trace_metadata,
        )
        trace_status = "ok"
        trace_output: dict[str, Any] | None = None
        try:
            route_scheduler_tick = _core_callable(
                "route_scheduler_tick", _default_route_scheduler_tick
            )
            result = await route_scheduler_tick(self, chat_id=chat_id, max_tasks=max_tasks)
            raw_result = str(result or "")
            user_visible_text = extract_heartbeat_user_visible_message(raw_result)
            normalized = normalize_plain_text(raw_result)
            normalized_upper = normalized.strip().upper()
            dispatch_summary = await self._dispatch_due_scheduled_tasks_once(
                chat_id=chat_id,
                max_tasks=max_tasks,
            )
            due_count = int(dispatch_summary.get("due_count") or 0)
            trace_metadata.update(
                {
                    "due_count": due_count,
                    "result_preview": safe_preview(normalized, limit=240),
                    "result_len": len(normalized or ""),
                    "dispatch_started": int(dispatch_summary.get("started") or 0),
                    "dispatch_completed": int(dispatch_summary.get("completed") or 0),
                    "dispatch_duplicates": int(dispatch_summary.get("duplicates") or 0),
                    "dispatch_rejected_by_policy": int(
                        dispatch_summary.get("rejected_by_policy") or 0
                    ),
                    "dispatch_policy_reasons": dict(dispatch_summary.get("policy_reasons") or {}),
                    "dispatch_errors": int(dispatch_summary.get("errors") or 0),
                }
            )
            counters = self._scheduler_metric_counters or _empty_scheduler_metric_counters()
            counters["ticks_total"] = int(counters.get("ticks_total", 0) or 0) + 1
            counters["started_total"] = int(counters.get("started_total", 0) or 0) + int(
                dispatch_summary.get("started") or 0
            )
            counters["completed_total"] = int(counters.get("completed_total", 0) or 0) + int(
                dispatch_summary.get("completed") or 0
            )
            counters["duplicates_total"] = int(counters.get("duplicates_total", 0) or 0) + int(
                dispatch_summary.get("duplicates") or 0
            )
            counters["rejected_by_policy_total"] = int(
                counters.get("rejected_by_policy_total", 0) or 0
            ) + int(dispatch_summary.get("rejected_by_policy") or 0)
            counters["errors_total"] = int(counters.get("errors_total", 0) or 0) + int(
                dispatch_summary.get("errors") or 0
            )
            self._scheduler_metric_counters = counters
            if normalized_upper in {"", "SCHEDULER_IDLE", "NO_USER_RESPONSE"}:
                proactive_result = await self._maybe_run_proactive_tick_once(
                    chat_id=chat_id,
                    dispatch_summary=dispatch_summary,
                    scheduler_result=normalized_upper or "EMPTY",
                )
                if proactive_result is not None:
                    trace_metadata.update(
                        {
                            "proactive_status": proactive_result.get("status"),
                            "proactive_reason": proactive_result.get("reason"),
                        }
                    )
                self._publish_scheduler_metrics(
                    running=True,
                    last_tick_status="idle",
                    due_count=due_count,
                    result_preview=safe_preview(normalized, limit=160),
                    dispatch_summary=dispatch_summary,
                )
                trace_output = {
                    "status": "idle",
                    "due_count": due_count,
                    "dispatch": dispatch_summary,
                    "proactive": proactive_result,
                }
                logger.debug(
                    "Scheduler tick complete",
                    due_count=due_count,
                    dispatch=dispatch_summary,
                    result=normalized_upper or "EMPTY",
                    proactive=proactive_result,
                )
                return

            if not user_visible_text:
                suppressed_reason = "control_or_missing_user_visible_wrapper"
                status = (
                    "idle"
                    if _has_scheduler_idle_suffix(normalized)
                    or has_no_user_response_suffix(normalized)
                    else "decision_ready"
                )
                trace_metadata.update(
                    {
                        "delivery_mode": DeliveryMode.SILENT,
                        "user_visible": False,
                        "suppressed_reason": suppressed_reason,
                    }
                )
                self._publish_scheduler_metrics(
                    running=True,
                    last_tick_status=status,
                    due_count=due_count,
                    result_preview=safe_preview(normalized, limit=160),
                    dispatch_summary=dispatch_summary,
                )
                trace_output = {
                    "status": status,
                    "due_count": due_count,
                    "result_preview": safe_preview(normalized, limit=160),
                    "user_visible_sent": False,
                    "suppressed_reason": suppressed_reason,
                    "dispatch": dispatch_summary,
                }
                logger.info(
                    "Scheduler tick produced non-user-visible decision",
                    due_count=due_count,
                    dispatch=dispatch_summary,
                    suppressed_reason=suppressed_reason,
                    result_preview=safe_preview(normalized, limit=160),
                )
                return

            delivery = resolve_user_delivery(user_visible_text)
            trace_metadata.update(
                {
                    "delivery_mode": delivery.mode,
                    "user_visible": delivery.user_visible,
                    "suppressed_reason": delivery.reason,
                }
            )
            user_visible_sent = False
            if delivery.user_visible:
                delivery_chat_id, delivery_target_source = self._resolve_scheduler_delivery_chat_id(
                    requested_chat_id=chat_id,
                )
                trace_metadata["delivery_target_source"] = delivery_target_source
                if delivery_chat_id is not None:
                    send_scheduler_control_update = _core_callable(
                        "_send_scheduler_control_update",
                        _default_send_scheduler_control_update,
                    )
                    await send_scheduler_control_update(
                        self,
                        delivery_chat_id,
                        None,
                        delivery.text,
                    )
                    user_visible_sent = True
                    trace_metadata["delivery_chat_id"] = delivery_chat_id
                else:
                    logger.warning(
                        "Scheduler tick produced user-visible text without delivery target",
                        result_preview=safe_preview(delivery.text, limit=160),
                    )

            self._publish_scheduler_metrics(
                running=True,
                last_tick_status="decision_ready",
                due_count=due_count,
                result_preview=safe_preview(normalized, limit=160),
                dispatch_summary=dispatch_summary,
            )
            trace_output = {
                "status": "decision_ready",
                "due_count": due_count,
                "result_preview": safe_preview(normalized, limit=160),
                "user_visible_sent": user_visible_sent,
                "dispatch": dispatch_summary,
            }
            logger.info(
                "Scheduler tick produced decision",
                due_count=due_count,
                dispatch=dispatch_summary,
                user_visible_sent=user_visible_sent,
                result_preview=safe_preview(normalized, limit=160),
            )
        except Exception as exc:
            counters = self._scheduler_metric_counters or _empty_scheduler_metric_counters()
            counters["ticks_total"] = int(counters.get("ticks_total", 0) or 0) + 1
            counters["failures_total"] = int(counters.get("failures_total", 0) or 0) + 1
            self._scheduler_metric_counters = counters
            self._publish_scheduler_metrics(
                running=True,
                last_tick_status="failed",
                result_preview=safe_preview(str(exc), limit=160),
            )
            trace_status = "error"
            trace_metadata.update(summarize_exception(exc))
            trace_output = {"status": "failed"}
            logger.exception("Scheduler tick failed")
        finally:
            runtime_settings = getattr(getattr(self, "runtime", None), "settings", None)
            if runtime_settings is not None:
                update_last_scheduler_tick = _core_callable(
                    "update_last_scheduler_tick",
                    _default_update_last_scheduler_tick,
                )
                await asyncio.to_thread(
                    update_last_scheduler_tick,
                    runtime_settings,
                    status=trace_status,
                )
            trace_metadata["duration_ms"] = round(now_ms() - trace_started_at_ms, 2)
            await _finish_background_trace_context(
                self.trace_sink,
                trace_ctx,
                trace_token,
                is_root_trace=is_root_trace,
                status=trace_status,
                output=trace_output,
                metadata=trace_metadata,
            )

    async def _maybe_run_proactive_tick_once(
        self,
        *,
        chat_id: int,
        dispatch_summary: dict[str, Any],
        scheduler_result: str,
    ) -> dict[str, Any] | None:
        proactive_tick_enabled = bool(
            _core_value("_PROACTIVE_TICK_ENABLED", _DEFAULT_PROACTIVE_TICK_ENABLED)
        )
        if not proactive_tick_enabled:
            return {"status": "skipped", "reason": "disabled"}

        due_count = int(dispatch_summary.get("due_count") or 0)
        started = int(dispatch_summary.get("started") or 0)
        errors = int(dispatch_summary.get("errors") or 0)
        rejected = int(dispatch_summary.get("rejected_by_policy") or 0)
        if due_count or started or errors or rejected:
            return {
                "status": "skipped",
                "reason": "scheduler_not_idle",
                "due_count": due_count,
                "started": started,
                "errors": errors,
                "rejected_by_policy": rejected,
            }

        now = utc_now()
        last_run_at = (self._last_proactive_tick_at_by_chat or {}).get(chat_id)
        min_interval_seconds = float(
            _core_value(
                "_PROACTIVE_TICK_MIN_INTERVAL_SECONDS",
                _DEFAULT_PROACTIVE_TICK_MIN_INTERVAL_SECONDS,
            )
        )
        if last_run_at is not None and min_interval_seconds > 0:
            try:
                elapsed = (now - last_run_at).total_seconds()
            except Exception:
                elapsed = min_interval_seconds
            if elapsed < min_interval_seconds:
                return {
                    "status": "skipped",
                    "reason": "cooldown",
                    "elapsed_seconds": round(elapsed, 2),
                    "min_interval_seconds": min_interval_seconds,
                }

        if self._last_proactive_tick_at_by_chat is None:
            self._last_proactive_tick_at_by_chat = {}
        self._last_proactive_tick_at_by_chat[chat_id] = now
        try:
            route_proactive_tick = _core_callable(
                "route_proactive_tick", _default_route_proactive_tick
            )
            result = await route_proactive_tick(
                self,
                chat_id=chat_id,
                reason=f"scheduler_idle:{scheduler_result}",
            )
        except Exception as exc:
            logger.warning("Proactive tick failed", chat_id=chat_id, error=str(exc), exc_info=True)
            return {
                "status": "error",
                "reason": "proactive_tick_failed",
                "error": str(exc),
            }
        return {
            "status": "ran",
            "reason": "scheduler_idle",
            "result_preview": safe_preview(str(result or ""), limit=240),
        }
