import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchIncidents } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";
import { formatLocalDateTime } from "../utils/dateTime";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

type IncidentsPayload = components["schemas"]["DashboardIncidentsV2"];
type IncidentItem = {
  id?: string;
  service?: string;
  severity?: string;
  impact?: number;
  title?: string;
  summary?: string;
  count?: number;
  latest_at?: string;
};

function severityTone(value?: string): string {
  const v = String(value ?? "").toLowerCase();
  if (v === "critical") {
    return "border-rose-300/30 bg-rose-500/10 text-rose-300";
  }
  if (v === "warning") {
    return "border-amber-300/30 bg-amber-500/10 text-amber-300";
  }
  return "border-emerald-400/30 bg-emerald-500/10 text-emerald-300";
}

function EmptyState({ title, message, tone = "neutral" }: { title: string; message: string; tone?: "neutral" | "error" }) {
  const className =
    tone === "error"
      ? "rounded-[30px] border border-rose-400/30 bg-rose-950/20 p-8 text-rose-100"
      : "rounded-[30px] border border-white/6 bg-[var(--surface-panel)] p-8 text-[var(--text-strong)]";

  return (
    <section className={className}>
      <h2 className="text-2xl font-semibold text-white">{title}</h2>
      <p className="mt-2 text-sm text-[var(--text-muted)]">{message}</p>
    </section>
  );
}

export function IncidentsPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<IncidentsPayload | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    void fetchIncidents({
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
    return <EmptyState title="Incidents" message="Loading incident stream..." />;
  }

  if (error) {
    return <EmptyState title="Incidents" message={`Failed to load incidents: ${error}`} tone="error" />;
  }

  const incidentsNode = (data?.incidents ?? {}) as {
    summary?: { open?: number; critical?: number; warning?: number };
    items?: IncidentItem[];
  };

  const summary = incidentsNode.summary ?? {};
  const items = incidentsNode.items ?? [];

  return (
    <section className="grid gap-6">
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_320px]">
        <Card className="rounded-[32px] border-white/6 bg-[var(--surface-panel)] py-0 shadow-[0_24px_80px_rgba(0,0,0,0.26)]">
          <CardContent className="px-6 py-6">
            <p className="text-[11px] uppercase tracking-[0.24em] text-[var(--text-dim)]">Incident groups</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">Open warning and critical signals</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--text-muted)]">
              Deduped operational issues grouped by title and service so the page stays readable under pressure.
            </p>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Open</p>
                <p className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-white">{summary.open ?? 0}</p>
              </div>
              <div className="rounded-[24px] border border-rose-300/20 bg-rose-500/5 p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-rose-100/70">Critical</p>
                <p className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-rose-200">{summary.critical ?? 0}</p>
              </div>
              <div className="rounded-[24px] border border-amber-300/20 bg-amber-500/5 p-4">
                <p className="text-[11px] uppercase tracking-[0.18em] text-amber-100/70">Warning</p>
                <p className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-amber-200">{summary.warning ?? 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[32px] border-white/6 bg-[var(--surface-panel)] py-0">
          <CardContent className="space-y-4 px-6 py-6">
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Operator read</p>
              <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">
                This view is intentionally quiet. It highlights active pressure without turning into another dense event log.
              </p>
            </div>
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Current scope</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  1 hour window
                </Badge>
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  all services
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {items.length === 0 ? (
        <Card className="rounded-[30px] border-white/6 bg-[var(--surface-panel)] py-0">
          <CardContent className="p-6">
            <p className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-[var(--text-muted)]">
              No incident groups in the current window.
            </p>
          </CardContent>
        </Card>
      ) : (
        <section className="grid gap-4 xl:grid-cols-2">
          {items.map((item) => (
            <article
              key={item.id ?? item.title}
              className="rounded-[28px] border border-white/6 bg-[var(--surface-panel)] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.2)]"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Badge variant="outline" className={`rounded-full ${severityTone(item.severity)}`}>
                  {String(item.severity ?? "unknown")}
                </Badge>
                <div className="text-xs text-[var(--text-dim)]">Impact {item.impact ?? 0}</div>
              </div>
              <h3 className="mt-4 text-xl font-semibold text-white">{item.title ?? "Incident"}</h3>
              <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">{item.summary ?? "No summary"}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  Service {item.service ?? "unknown"}
                </Badge>
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  Count {item.count ?? 0}
                </Badge>
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  {formatLocalDateTime(item.latest_at)}
                </Badge>
              </div>
            </article>
          ))}
        </section>
      )}
    </section>
  );
}
