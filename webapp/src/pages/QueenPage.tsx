import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchQueen } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";

type QueenPayload = components["schemas"]["DashboardQueenV2"];
type QueenView = {
  state?: string;
  followup_queues?: number;
  internal_queues?: number;
  followup_tasks?: number;
  internal_tasks?: number;
};
type QueuesView = {
  telegram_send_tasks?: number;
  telegram_queues?: number;
  exec_sessions_running?: number;
  exec_sessions_total?: number;
};
type ControlView = {
  pending_requests?: number;
  last_ack?: { timestamp?: string; request_id?: string; status?: string };
};
type HealthView = {
  status?: string;
  summary?: string;
  reasons?: string[];
};

function tone(value?: string): string {
  const v = String(value ?? "").toLowerCase();
  if (v === "ok" || v === "idle") {
    return "tone-ok";
  }
  if (v === "warning" || v === "thinking") {
    return "tone-warn";
  }
  return "tone-bad";
}

function metric(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
}

export function QueenPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<QueenPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    void fetchQueen({
      windowMinutes: filters.windowMinutes,
      service: filters.service,
      environment: filters.environment,
      token: filters.token || undefined,
    })
      .then((payload) => {
        if (active) {
          setData(payload);
        }
      })
      .catch((err: unknown) => {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Unknown request error");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [filters.environment, filters.service, filters.token, filters.windowMinutes]);

  if (loading) {
    return (
      <section className="panel">
        <h2>Queen</h2>
        <p>Loading Queen operational state...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel panel-error">
        <h2>Queen</h2>
        <p>Failed to load queen telemetry: {error}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="panel">
        <h2>Queen</h2>
        <p>No data returned.</p>
      </section>
    );
  }

  const queen = (data.queen ?? {}) as QueenView;
  const queues = (data.queues ?? {}) as QueuesView;
  const control = (data.control ?? {}) as ControlView;
  const health = (data.health ?? {}) as HealthView;
  const lastAck = control.last_ack ?? {};

  return (
    <section className="panel">
      <h2>Queen</h2>
      <p className="overview-meta">Operational state for orchestration core and control pressure.</p>

      <article className="headline-card">
        <div className={`headline-status ${tone(queen.state)}`}>{String(queen.state ?? "unknown").toUpperCase()}</div>
        <div>
          <h3>{health.summary ?? "No health summary"}</h3>
          <p>{(health.reasons ?? []).join(" | ") || "No active degradation reasons."}</p>
        </div>
      </article>

      <div className="kpi-grid">
        <article className="kpi-card">
          <h4>Followup Queues</h4>
          <strong>{metric(queen.followup_queues)}</strong>
        </article>
        <article className="kpi-card">
          <h4>Internal Queues</h4>
          <strong>{metric(queen.internal_queues)}</strong>
        </article>
        <article className="kpi-card">
          <h4>Followup Tasks</h4>
          <strong>{metric(queen.followup_tasks)}</strong>
        </article>
        <article className="kpi-card">
          <h4>Internal Tasks</h4>
          <strong>{metric(queen.internal_tasks)}</strong>
        </article>
      </div>

      <div className="overview-columns">
        <article className="mini-panel">
          <h4>Queues and Sessions</h4>
          <p>Telegram queues: {metric(queues.telegram_queues)}</p>
          <p>Telegram send tasks: {metric(queues.telegram_send_tasks)}</p>
          <p>Exec sessions running: {metric(queues.exec_sessions_running)}</p>
          <p>Exec sessions total: {metric(queues.exec_sessions_total)}</p>
        </article>

        <article className="mini-panel">
          <h4>Control Channel</h4>
          <p>Pending requests: {metric(control.pending_requests)}</p>
          <p>Last ack request: {metric(lastAck.request_id)}</p>
          <p>Last ack status: <span className={tone(lastAck.status)}>{metric(lastAck.status)}</span></p>
          <p>Last ack timestamp: {metric(lastAck.timestamp)}</p>
        </article>
      </div>
    </section>
  );
}

