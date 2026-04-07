import { useEffect, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchOverview } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";
import { formatLocalDateTime } from "../utils/dateTime";

type OverviewPayload = components["schemas"]["DashboardOverviewV2"];
type KpiItem = { value?: unknown; unit?: string; status?: string };
type HealthView = { status?: string; summary?: string; reasons?: string[] };
type ServiceView = { id?: string; name?: string; status?: string; reason?: string; updated_at?: string };

function statusTone(status?: string): string {
  const value = String(status ?? "").toLowerCase();
  if (value === "ok") {
    return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  }
  if (value === "warning") {
    return "border-amber-300/20 bg-amber-300/10 text-amber-100";
  }
  return "border-rose-300/20 bg-rose-400/10 text-rose-100";
}

function dotTone(status?: string): string {
  const value = String(status ?? "").toLowerCase();
  if (value === "ok") {
    return "bg-emerald-400";
  }
  if (value === "warning") {
    return "bg-amber-300";
  }
  return "bg-rose-400";
}

function formatKpi(value: unknown, unit?: string): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return unit ? `${String(value)} ${unit}` : String(value);
}

function EmptyState({ title, message, tone = "neutral" }: { title: string; message: string; tone?: "neutral" | "error" }) {
  const sectionClassName =
    tone === "error"
      ? "rounded-[30px] border border-rose-400/30 bg-rose-950/20 p-8 text-rose-100"
      : "rounded-[30px] border border-white/6 bg-[var(--surface-panel)] p-8 text-[var(--text-strong)]";

  return (
    <section className={sectionClassName}>
      <h2 className="text-2xl font-semibold text-white">{title}</h2>
      <p className="mt-2 text-sm text-[var(--text-muted)]">{message}</p>
    </section>
  );
}

function MetricTile({ label, metric }: { label: string; metric?: KpiItem }) {
  return (
    <article className="rounded-[26px] border border-white/6 bg-[var(--surface-panel-strong)] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">{label}</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-white">
            {formatKpi(metric?.value, metric?.unit)}
          </p>
        </div>
        <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] ${statusTone(metric?.status)}`}>
          {String(metric?.status ?? "unknown")}
        </span>
      </div>
    </article>
  );
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
          setError(err instanceof Error ? err.message : "Unknown request error");
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
  const services = ((data?.services ?? []) as ServiceView[]).slice(0, 8);
  const reasons = (health.reasons ?? []).filter(Boolean);

  if (loading) {
    return <EmptyState title="Overview" message="Loading operational snapshot..." />;
  }

  if (error) {
    return <EmptyState title="Overview" message={`Failed to load overview: ${error}`} tone="error" />;
  }

  if (!data) {
    return <EmptyState title="Overview" message="No data returned." />;
  }

  return (
    <section className="grid gap-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_360px]">
        <article className="overflow-hidden rounded-[34px] border border-white/6 bg-[linear-gradient(135deg,rgba(31,41,55,0.96),rgba(17,24,39,0.84))] p-6 shadow-[0_32px_90px_rgba(0,0,0,0.3)] md:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <p className="text-[11px] uppercase tracking-[0.24em] text-[var(--text-dim)]">Current health</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white md:text-4xl">
                {health.summary ?? "Operational summary"}
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
                {reasons.length > 0
                  ? reasons.join(" | ")
                  : "No degradation reasons reported for the current filter scope."}
              </p>
            </div>
            <span
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.18em] ${statusTone(health.status)}`}
            >
              <span className={`h-2.5 w-2.5 rounded-full ${dotTone(health.status)}`} />
              {String(health.status ?? "unknown")}
            </span>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <div className="rounded-[26px] border border-white/6 bg-white/[0.04] px-4 py-4">
              <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">Open incidents</p>
              <p className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-white">{incidentsSummary.open}</p>
              <p className="mt-2 text-sm text-[var(--text-muted)]">Across the current filter window.</p>
            </div>
            <div className="rounded-[26px] border border-rose-300/10 bg-rose-400/[0.05] px-4 py-4">
              <p className="text-[11px] uppercase tracking-[0.2em] text-rose-100/70">Critical</p>
              <p className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-rose-50">{incidentsSummary.critical}</p>
              <p className="mt-2 text-sm text-rose-100/60">Needs immediate attention.</p>
            </div>
            <div className="rounded-[26px] border border-amber-200/10 bg-amber-300/[0.05] px-4 py-4">
              <p className="text-[11px] uppercase tracking-[0.2em] text-amber-100/70">Warning</p>
              <p className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-amber-50">{incidentsSummary.warning}</p>
              <p className="mt-2 text-sm text-amber-100/60">Watchlist items still active.</p>
            </div>
          </div>
        </article>

        <aside className="rounded-[34px] border border-white/6 bg-[var(--surface-panel)] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.26)]">
          <p className="text-[11px] uppercase tracking-[0.22em] text-[var(--text-dim)]">Snapshot</p>
          <div className="mt-5 space-y-5">
            <div className="border-b border-white/6 pb-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Generated</div>
              <div className="mt-2 text-lg font-semibold text-white">{formatLocalDateTime(data.generated_at)}</div>
            </div>
            <div className="border-b border-white/6 pb-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Scope</div>
              <div className="mt-2 text-sm text-[var(--text-strong)]">Dashboard-wide live view</div>
              <div className="mt-1 text-sm text-[var(--text-muted)]">1 hour window across all services and environments.</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Why this matters</div>
              <div className="mt-3 space-y-2">
                {(reasons.length > 0 ? reasons.slice(0, 4) : ["No active degradation reasons reported."]).map((reason) => (
                  <div key={reason} className="rounded-2xl border border-white/6 bg-white/[0.03] px-3 py-3 text-sm text-[var(--text-muted)]">
                    {reason}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </aside>
      </section>

      <section className="grid gap-4 xl:grid-cols-4">
        <MetricTile label="Latency p95" metric={kpis.latency_ms_p95} />
        <MetricTile label="Error rate" metric={kpis.error_rate_5m} />
        <MetricTile label="Queue depth" metric={kpis.queue_depth} />
        <MetricTile label="Active workers" metric={kpis.active_workers} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <article className="rounded-[30px] border border-white/6 bg-[var(--surface-panel)] p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">Incident mix</p>
              <h3 className="mt-2 text-xl font-semibold text-white">Current pressure</h3>
            </div>
            <span className="text-sm text-[var(--text-muted)]">{incidentsSummary.open} open</span>
          </div>
          <div className="mt-6 space-y-4">
            <div>
              <div className="mb-2 flex items-center justify-between text-sm text-[var(--text-muted)]">
                <span>Critical</span>
                <span>{incidentsSummary.critical}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
                <div
                  className="h-full rounded-full bg-rose-400/80"
                  style={{
                    width: `${incidentsSummary.open > 0 ? (incidentsSummary.critical / incidentsSummary.open) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between text-sm text-[var(--text-muted)]">
                <span>Warning</span>
                <span>{incidentsSummary.warning}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
                <div
                  className="h-full rounded-full bg-amber-300/80"
                  style={{
                    width: `${incidentsSummary.open > 0 ? (incidentsSummary.warning / incidentsSummary.open) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          </div>
          <div className="mt-6 rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] px-4 py-4 text-sm text-[var(--text-muted)]">
            This block stays intentionally quiet: it shows pressure distribution without fighting the primary health summary.
          </div>
        </article>

        <article className="rounded-[30px] border border-white/6 bg-[var(--surface-panel)] p-5">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/6 pb-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">Service health</p>
              <h3 className="mt-2 text-xl font-semibold text-white">What needs attention now</h3>
            </div>
            <p className="text-sm text-[var(--text-muted)]">Newest services in scope</p>
          </div>
          <div className="mt-4 space-y-3">
            {services.length === 0 ? (
              <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-sm text-[var(--text-muted)]">
                No services returned.
              </div>
            ) : (
              services.map((service) => (
                <article
                  key={String(service.id ?? service.name ?? "service")}
                  className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] px-4 py-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        <span className={`h-2.5 w-2.5 rounded-full ${dotTone(service.status)}`} />
                        <h4 className="text-base font-semibold text-white">{service.name ?? "Service"}</h4>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
                        {service.reason ?? "No reason provided"}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] ${statusTone(service.status)}`}>
                        {String(service.status ?? "unknown")}
                      </span>
                      <div className="mt-2 text-xs text-[var(--text-dim)]">{formatLocalDateTime(service.updated_at)}</div>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </article>
      </section>
    </section>
  );
}
