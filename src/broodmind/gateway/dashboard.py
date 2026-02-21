from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from broodmind.config.settings import Settings
from broodmind.runtime_metrics import read_metrics_snapshot
from broodmind.state import is_pid_running, read_status
from broodmind.store.sqlite import SQLiteStore


def register_dashboard_routes(app: FastAPI) -> None:
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page() -> str:
        return _dashboard_html()

    @app.get("/api/dashboard/snapshot")
    async def dashboard_snapshot(
        request: Request,
        last: int = Query(8, ge=1, le=50),
    ) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        store = _get_store(app, settings)
        return _build_snapshot(settings, store, last)

    @app.get("/api/dashboard/logs")
    async def dashboard_logs(
        request: Request,
        lines: int = Query(50, ge=1, le=500),
    ) -> dict[str, Any]:
        settings = _get_settings(app)
        _verify_dashboard_token(request, settings)
        log_path = settings.state_dir / "logs" / "broodmind.log"
        entries: list[dict[str, str]] = []
        for line in _read_last_lines(log_path, max_lines=lines):
            raw = line.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                entries.append({"event": raw[:200], "level": "info"})
                continue
            if isinstance(data, dict):
                entries.append(
                    {
                        "event": str(data.get("event", ""))[:200],
                        "level": str(data.get("level", "info")),
                        "timestamp": str(data.get("timestamp", "")),
                    }
                )
        return {"count": len(entries), "entries": entries}

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


def _build_snapshot(settings: Settings, store: SQLiteStore, last: int) -> dict[str, Any]:
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
    recent_logs = _tail_logs(log_path, 12)

    return {
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
        "connectivity": {"mcp_servers": connectivity_metrics.get("mcp_servers", {})},
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
            "completed": by_status.get("completed", 0),
            "failed": by_status.get("failed", 0),
            "stopped": by_status.get("stopped", 0),
            "recent": [
                {
                    "id": w.id,
                    "status": w.status,
                    "task": w.task,
                    "updated_at": w.updated_at.isoformat(),
                    "summary": w.summary or "",
                    "error": w.error or "",
                    "tools_used": w.tools_used or [],
                }
                for w in recent_workers[:last]
            ],
        },
        "control": {
            "pending_requests": len(pending_requests),
            "last_ack": last_ack,
        },
    }


def _tail_logs(path: Path, max_lines: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in _read_last_lines(path, max_lines=max_lines):
        raw = line.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            out.append({"event": raw[:120], "level": "info"})
            continue
        if not isinstance(data, dict):
            continue
        out.append(
            {
                "event": str(data.get("event", ""))[:120],
                "level": str(data.get("level", "info")),
            }
        )
    return out


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
  <title>BroodMind Dashboard</title>
  <style>
    :root {
      --bg0: #0f172a;
      --bg1: #1e293b;
      --card: #111827;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --ok: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
      --accent: #38bdf8;
      --border: #334155;
      --font: "Segoe UI", "SF Pro Text", -apple-system, BlinkMacSystemFont, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: var(--font);
      color: var(--text);
      background: radial-gradient(circle at 20% 20%, #1d4ed8 0%, transparent 35%), linear-gradient(160deg, var(--bg0), var(--bg1));
      min-height: 100vh;
    }
    .shell { max-width: 1200px; margin: 0 auto; padding: 18px; }
    .top { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    .title { font-size: 22px; letter-spacing: 0.5px; }
    .token-wrap { display: flex; gap: 8px; }
    input, button {
      background: #0b1220;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
    }
    button { cursor: pointer; }
    button:hover { border-color: var(--accent); }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 10px; }
    .card {
      background: rgba(10, 17, 31, 0.86);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      backdrop-filter: blur(4px);
    }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
    .value { font-size: 22px; font-weight: 600; }
    .ok { color: var(--ok); }
    .warn { color: var(--warn); }
    .bad { color: var(--bad); }
    .row { margin-top: 12px; display: grid; grid-template-columns: 2fr 1fr; gap: 10px; }
    .mono { font-family: Consolas, "Courier New", monospace; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px; border-bottom: 1px solid #1f2937; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    .logs { max-height: 340px; overflow: auto; }
    .log-line { border-bottom: 1px solid #1f2937; padding: 6px 0; font-size: 13px; }
    .muted { color: var(--muted); }
    @media (max-width: 1000px) {
      .grid { grid-template-columns: repeat(2, minmax(160px, 1fr)); }
      .row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="top">
      <div class="title">BroodMind Dashboard</div>
      <div class="token-wrap">
        <input id="token" type="password" placeholder="Dashboard token (optional)" />
        <button id="save-token">Save token</button>
        <button id="refresh">Refresh</button>
      </div>
    </div>
    <div class="grid">
      <div class="card"><div class="label">System</div><div id="system-running" class="value">-</div></div>
      <div class="card"><div class="label">Queen</div><div id="queen-state" class="value">-</div></div>
      <div class="card"><div class="label">Workers Running</div><div id="workers-running" class="value">-</div></div>
      <div class="card"><div class="label">Pending Control</div><div id="control-pending" class="value">-</div></div>
    </div>
    <div class="row">
      <div class="card">
        <div class="label">Recent Workers</div>
        <table>
          <thead><tr><th>ID</th><th>Status</th><th>Task</th><th>Updated</th></tr></thead>
          <tbody id="workers-table"><tr><td colspan="4" class="muted">No data</td></tr></tbody>
        </table>
      </div>
      <div class="card">
        <div class="label">Recent Events</div>
        <div id="logs" class="logs muted">No data</div>
      </div>
    </div>
    <div class="muted mono" id="meta" style="margin-top: 10px;">Last refresh: never</div>
  </div>
  <script>
    const tokenInput = document.getElementById("token");
    const saveBtn = document.getElementById("save-token");
    const refreshBtn = document.getElementById("refresh");
    const tokenKey = "broodmind.dashboard.token";
    tokenInput.value = localStorage.getItem(tokenKey) || "";

    saveBtn.addEventListener("click", () => {
      localStorage.setItem(tokenKey, tokenInput.value || "");
      runOnce();
    });
    refreshBtn.addEventListener("click", runOnce);

    function headers() {
      const token = tokenInput.value || "";
      return token ? { "x-broodmind-token": token } : {};
    }

    function statusClass(value) {
      const v = String(value || "").toLowerCase();
      if (["running", "idle", "thinking", "connected", "ok", "completed"].includes(v)) return "ok";
      if (["warning", "stopped"].includes(v)) return "warn";
      return "bad";
    }

    function setText(id, text, cls) {
      const el = document.getElementById(id);
      el.textContent = text;
      el.className = "value " + (cls || "");
    }

    async function runOnce() {
      try {
        const rsp = await fetch("/api/dashboard/snapshot?last=12", { headers: headers() });
        if (!rsp.ok) {
          throw new Error("API " + rsp.status);
        }
        const data = await rsp.json();
        setText("system-running", data.system.running ? "RUNNING" : "STOPPED", data.system.running ? "ok" : "bad");
        setText("queen-state", data.queen.state, statusClass(data.queen.state));
        setText("workers-running", String(data.workers.running), data.workers.running > 0 ? "ok" : "warn");
        setText("control-pending", String(data.control.pending_requests), data.control.pending_requests > 0 ? "warn" : "ok");

        const rows = (data.workers.recent || []).map((w) =>
          "<tr><td class='mono'>" + esc(w.id) + "</td><td>" + esc(w.status) + "</td><td>" + esc(w.task) + "</td><td class='mono'>" + esc(w.updated_at) + "</td></tr>"
        );
        document.getElementById("workers-table").innerHTML = rows.length ? rows.join("") : "<tr><td colspan='4' class='muted'>No workers</td></tr>";

        const logHtml = (data.logs || []).map((l) => {
          const level = String(l.level || "info").toLowerCase();
          const color = level === "error" ? "var(--bad)" : (level === "warning" ? "var(--warn)" : "var(--text)");
          return "<div class='log-line'><span style='color:" + color + ";'>" + esc(level) + "</span> " + esc(l.event || "") + "</div>";
        });
        document.getElementById("logs").innerHTML = logHtml.length ? logHtml.join("") : "<div class='muted'>No logs</div>";

        document.getElementById("meta").textContent =
          "Last refresh: " + new Date().toLocaleString() +
          " | Channel: " + (data.system.active_channel || "Unknown") +
          " | Uptime: " + (data.system.uptime || "N/A");
      } catch (err) {
        document.getElementById("meta").textContent = "Dashboard error: " + err;
      }
    }

    function esc(v) {
      return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    }

    runOnce();
    setInterval(runOnce, 2000);
  </script>
</body>
</html>
"""
