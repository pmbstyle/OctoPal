import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchOverview } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";

type OverviewPayload = components["schemas"]["DashboardOverviewV2"];
type KpiItem = { value?: unknown; unit?: string; status?: string };
type HealthView = { status?: string; summary?: string; reasons?: string[] };
type ServiceView = { id?: string; name?: string; status?: string; reason?: string };

function statusClass(status: string | undefined): string {
  const value = String(status ?? "").toLowerCase();
  if (value === "ok") {
    return "tone-ok";
  }
  if (value === "warning") {
    return "tone-warn";
  }
  return "tone-bad";
}

function formatKpi(value: unknown, unit?: string): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return unit ? `${String(value)} ${unit}` : String(value);
}

export function OverviewPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<OverviewPayload | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let active = true;
    let source: EventSource | null = null;

    const query = new URLSearchParams();
    query.set("window_minutes", String(filters.windowMinutes));
    query.set("service", filters.service);
    query.set("environment", filters.environment);
    query.set("topic", "overview");
    query.set("interval_seconds", "2");
    if (filters.token) {
      query.set("token", filters.token);
    }

    const loadOnce = async () => {
      setLoading(true);
      setError("");
      try {
        const payload = await fetchOverview({
          windowMinutes: filters.windowMinutes,
          service: filters.service,
          environment: filters.environment,
          token: filters.token || undefined,
        });
        if (active) {
          setData(payload);
        }
      } catch (err: unknown) {
        if (active) {
          const message = err instanceof Error ? err.message : "Unknown request error";
          setError(message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void loadOnce();

    const pollTimer = window.setInterval(() => {
      void loadOnce();
    }, 15000);

    if (typeof EventSource !== "undefined") {
      source = new EventSource(`/api/dashboard/v2/stream?${query.toString()}`);
      source.addEventListener("overview", (event: MessageEvent) => {
        if (!active) {
          return;
        }
        try {
          const payload = JSON.parse(event.data) as OverviewPayload;
          setData(payload);
          setError("");
          setLoading(false);
        } catch (_error) {
          // Keep current data when stream payload is malformed.
        }
      });
      source.onerror = () => {
        if (active) {
          // Fallback polling already running; no extra action needed.
        }
      };
    }

    return () => {
      active = false;
      if (source) {
        source.close();
      }
      window.clearInterval(pollTimer);
    };
  }, [filters.environment, filters.service, filters.token, filters.windowMinutes]);

  const incidentsSummary = useMemo(() => {
    if (!data) {
      return { open: 0, critical: 0, warning: 0 };
    }
    return data.incidents_summary;
  }, [data]);

  const health = (data?.health ?? {}) as HealthView;
  const kpis = (data?.kpis ?? {}) as Record<string, KpiItem>;
  const services = ((data?.services ?? []) as ServiceView[]).slice(0, 5);

  if (loading) {
    return (
      <section className="panel">
        <h2>Overview</h2>
        <p>Loading operational snapshot...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel panel-error">
        <h2>Overview</h2>
        <p>Failed to load overview: {error}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="panel">
        <h2>Overview</h2>
        <p>No data returned.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Overview</h2>
      <p className="overview-meta">
        Incident-first summary for current filters. Generated at {data.generated_at}.
      </p>

      <article className="headline-card">
        <div className={`headline-status ${statusClass(health.status)}`}>
          {(health.status ?? "unknown").toUpperCase()}
        </div>
        <div>
          <h3>{health.summary ?? "No health summary"}</h3>
          <p>{(health.reasons ?? []).join(" | ") || "No degradation reasons."}</p>
        </div>
      </article>

      <div className="kpi-grid">
        <article className="kpi-card">
          <h4>Latency p95</h4>
          <strong>{formatKpi(kpis.latency_ms_p95?.value, kpis.latency_ms_p95?.unit)}</strong>
          <span className={statusClass(kpis.latency_ms_p95?.status)}>{kpis.latency_ms_p95?.status}</span>
        </article>
        <article className="kpi-card">
          <h4>Error Rate</h4>
          <strong>{formatKpi(kpis.error_rate_5m?.value, kpis.error_rate_5m?.unit)}</strong>
          <span className={statusClass(kpis.error_rate_5m?.status)}>{kpis.error_rate_5m?.status}</span>
        </article>
        <article className="kpi-card">
          <h4>Queue Depth</h4>
          <strong>{formatKpi(kpis.queue_depth?.value, kpis.queue_depth?.unit)}</strong>
          <span className={statusClass(kpis.queue_depth?.status)}>{kpis.queue_depth?.status}</span>
        </article>
        <article className="kpi-card">
          <h4>Active Workers</h4>
          <strong>{formatKpi(kpis.active_workers?.value, kpis.active_workers?.unit)}</strong>
          <span className={statusClass(kpis.active_workers?.status)}>{kpis.active_workers?.status}</span>
        </article>
      </div>

      <div className="overview-columns">
        <article className="mini-panel">
          <h4>Incident Summary</h4>
          <p>Open: {incidentsSummary.open}</p>
          <p>Critical: {incidentsSummary.critical}</p>
          <p>Warning: {incidentsSummary.warning}</p>
        </article>

        <article className="mini-panel">
          <h4>Service Health</h4>
          <ul className="plain-list">
            {services.map((service) => (
              <li key={String(service.id ?? service.name ?? "service")}>
                <span className={statusClass(service.status)}>{String(service.status ?? "unknown").toUpperCase()}</span>{" "}
                {service.name ?? "Service"}: {service.reason ?? "No reason"}
              </li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}
