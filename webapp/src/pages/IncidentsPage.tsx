import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchIncidents } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";

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

function severityClass(value?: string): string {
  const v = String(value ?? "").toLowerCase();
  if (v === "critical") {
    return "tone-bad";
  }
  if (v === "warning") {
    return "tone-warn";
  }
  return "tone-ok";
}

export function IncidentsPage() {
  const { filters, setFilters } = useOutletContext<AppShellOutletContext>();
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
    return (
      <section className="panel">
        <h2>Incidents</h2>
        <p>Loading incident stream...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel panel-error">
        <h2>Incidents</h2>
        <p>Failed to load incidents: {error}</p>
      </section>
    );
  }

  const incidentsNode = (data?.incidents ?? {}) as {
    summary?: { open?: number; critical?: number; warning?: number };
    items?: IncidentItem[];
  };

  const summary = incidentsNode.summary ?? {};
  const items = incidentsNode.items ?? [];

  return (
    <section className="panel">
      <h2>Incidents</h2>
      <p className="overview-meta">
        Open: {summary.open ?? 0} | Critical: {summary.critical ?? 0} | Warning: {summary.warning ?? 0}
      </p>

      {items.length === 0 ? (
        <article className="mini-panel">
          <h4>No incidents</h4>
          <p>No incident groups for current filters.</p>
        </article>
      ) : (
        <div className="incident-list">
          {items.map((item) => (
            <article key={item.id ?? item.title} className="incident-card">
              <div className="incident-head">
                <strong className={severityClass(item.severity)}>
                  {String(item.severity ?? "unknown").toUpperCase()}
                </strong>
                <span>Impact {item.impact ?? 0}</span>
              </div>
              <h4>{item.title ?? "Incident"}</h4>
              <p>{item.summary ?? "No summary"}</p>
              <p className="incident-meta">
                Service: <strong>{item.service ?? "unknown"}</strong> | Count: {item.count ?? 0}
              </p>
              <button
                type="button"
                className="drill-btn"
                onClick={() =>
                  setFilters({
                    ...filters,
                    service: (item.service as AppShellOutletContext["filters"]["service"]) || "all",
                  })
                }
              >
                Drill by service
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

