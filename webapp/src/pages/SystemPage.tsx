import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchSystem } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";

type SystemPayload = components["schemas"]["DashboardSystemV2"];
type ServiceItem = { id?: string; name?: string; status?: string; reason?: string; updated_at?: string };
type LogItem = { timestamp?: string; level?: string; event?: string; service?: string };
type Connectivity = {
  mcp_servers?: Record<string, { status?: string; tool_count?: number; name?: string }>;
};

function tone(status?: string): string {
  const v = String(status ?? "").toLowerCase();
  if (v === "ok" || v === "connected" || v === "running") {
    return "tone-ok";
  }
  if (v === "warning") {
    return "tone-warn";
  }
  return "tone-bad";
}

export function SystemPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<SystemPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    void fetchSystem({
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
        <h2>System</h2>
        <p>Loading system diagnostics...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel panel-error">
        <h2>System</h2>
        <p>Failed to load system diagnostics: {error}</p>
      </section>
    );
  }

  const system = (data?.system ?? {}) as { running?: boolean; pid?: number; uptime?: string; active_channel?: string };
  const services = ((data?.services ?? []) as ServiceItem[]).slice(0, 10);
  const logs = ((data?.logs ?? []) as LogItem[]).slice(0, 10);
  const connectivity = (data?.connectivity ?? {}) as Connectivity;
  const mcpServers = connectivity.mcp_servers ?? {};

  return (
    <section className="panel">
      <h2>System</h2>
      <p className="overview-meta">
        Runtime: <span className={tone(system.running ? "running" : "critical")}>{system.running ? "RUNNING" : "DOWN"}</span>{" "}
        | PID: {system.pid ?? "n/a"} | Channel: {system.active_channel ?? "n/a"} | Uptime: {system.uptime ?? "n/a"}
      </p>

      <div className="overview-columns">
        <article className="mini-panel">
          <h4>Service Health</h4>
          {services.length === 0 ? (
            <p>No services.</p>
          ) : (
            <ul className="plain-list">
              {services.map((service) => (
                <li key={service.id ?? service.name}>
                  <span className={tone(service.status)}>{String(service.status ?? "unknown").toUpperCase()}</span>{" "}
                  {service.name ?? "Service"}: {service.reason ?? "No reason"}
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="mini-panel">
          <h4>MCP Connectivity</h4>
          {Object.keys(mcpServers).length === 0 ? (
            <p>No MCP servers configured.</p>
          ) : (
            <ul className="plain-list">
              {Object.entries(mcpServers).map(([key, value]) => (
                <li key={key}>
                  <span className={tone(value.status)}>{String(value.status ?? "unknown").toUpperCase()}</span>{" "}
                  {value.name ?? key} | tools: {value.tool_count ?? 0}
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>

      <article className="mini-panel" style={{ marginTop: "10px" }}>
        <h4>Recent Logs</h4>
        {logs.length === 0 ? (
          <p>No logs in current filter window.</p>
        ) : (
          <ul className="plain-list">
            {logs.map((log) => (
              <li key={`${log.timestamp ?? ""}-${log.event ?? ""}`}>
                <span className={tone(log.level)}>{String(log.level ?? "info").toUpperCase()}</span>{" "}
                [{log.service ?? "gateway"}] {log.event ?? ""} ({log.timestamp ?? "n/a"})
              </li>
            ))}
          </ul>
        )}
      </article>
    </section>
  );
}

