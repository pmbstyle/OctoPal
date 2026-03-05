import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchWorkers } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";

type WorkersPayload = components["schemas"]["DashboardWorkersV2"];
type WorkerItem = {
  id?: string;
  template_name?: string;
  status?: string;
  task?: string;
  updated_at?: string;
  error?: string;
  parent_worker_id?: string | null;
  spawn_depth?: number;
};

function tone(status?: string): string {
  const v = String(status ?? "").toLowerCase();
  if (v === "completed" || v === "running" || v === "started") {
    return "tone-ok";
  }
  if (v === "warning" || v === "stopped") {
    return "tone-warn";
  }
  return "tone-bad";
}

function short(value?: string): string {
  if (!value) {
    return "n/a";
  }
  return value.includes("-") ? value.split("-")[0] : value.slice(0, 8);
}

export function WorkersPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<WorkersPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    void fetchWorkers({
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
        <h2>Workers</h2>
        <p>Loading workers...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel panel-error">
        <h2>Workers</h2>
        <p>Failed to load workers: {error}</p>
      </section>
    );
  }

  const workersNode = (data?.workers ?? {}) as {
    running?: number;
    root_running?: number;
    subworkers_running?: number;
    completed?: number;
    failed?: number;
    recent?: WorkerItem[];
    topology?: WorkerItem[];
  };

  const recent = workersNode.recent ?? [];
  const topology = workersNode.topology ?? [];

  return (
    <section className="panel">
      <h2>Workers</h2>
      <p className="overview-meta">
        Running: {workersNode.running ?? 0} | Root: {workersNode.root_running ?? 0} | Subworkers:{" "}
        {workersNode.subworkers_running ?? 0} | Failed: {workersNode.failed ?? 0}
      </p>

      <div className="overview-columns">
        <article className="mini-panel">
          <h4>Recent Workers</h4>
          {recent.length === 0 ? (
            <p>No recent workers.</p>
          ) : (
            <div className="workers-table-wrap">
              <table className="workers-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>Template</th>
                    <th>Task</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.slice(0, 12).map((worker) => (
                    <tr key={worker.id ?? worker.updated_at}>
                      <td>{short(worker.id)}</td>
                      <td className={tone(worker.status)}>{String(worker.status ?? "unknown")}</td>
                      <td>{worker.template_name ?? "n/a"}</td>
                      <td title={worker.task ?? ""}>{String(worker.task ?? "").slice(0, 64) || "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <article className="mini-panel">
          <h4>Topology Snapshot</h4>
          {topology.length === 0 ? (
            <p>No active topology nodes.</p>
          ) : (
            <ul className="plain-list">
              {topology.slice(0, 20).map((node) => (
                <li key={node.id ?? node.updated_at}>
                  <span style={{ marginLeft: `${Math.min(64, (node.spawn_depth ?? 0) * 12)}px` }}>
                    <strong>{short(node.id)}</strong> [{String(node.status ?? "unknown")}]{" "}
                    {node.parent_worker_id ? `child of ${short(node.parent_worker_id)}` : "root"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>
    </section>
  );
}

