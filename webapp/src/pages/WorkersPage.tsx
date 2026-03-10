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
  summary?: string;
  error?: string;
  result_preview?: string;
  output?: Record<string, unknown> | null;
  tools_used?: string[];
  lineage_id?: string | null;
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
  const [expandedWorkerId, setExpandedWorkerId] = useState<string>("");

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
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.slice(0, 12).flatMap((worker, index) => {
                    const workerKey = worker.id ?? worker.updated_at ?? `worker-${index}`;
                    const workerId = worker.id ?? "";
                    const isExpanded = expandedWorkerId === worker.id;
                    const preview = worker.result_preview?.trim() || "No result yet";
                    return [
                      <tr
                        key={`${workerKey}-row`}
                        className="cursor-pointer align-top"
                        onClick={() => {
                          if (!workerId) {
                            return;
                          }
                          setExpandedWorkerId((current) => (current === workerId ? "" : workerId));
                        }}
                      >
                        <td>{short(worker.id)}</td>
                        <td className={tone(worker.status)}>{String(worker.status ?? "unknown")}</td>
                        <td>{worker.template_name ?? "n/a"}</td>
                        <td title={worker.task ?? ""}>{String(worker.task ?? "").slice(0, 64) || "n/a"}</td>
                        <td title={preview} className="max-w-xs">
                          <div className="text-sm text-slate-300">
                            {preview.length > 88 ? `${preview.slice(0, 88)}...` : preview}
                          </div>
                        </td>
                      </tr>,
                      isExpanded ? (
                        <tr key={`${workerKey}-details`}>
                          <td colSpan={5} className="bg-slate-900/70">
                            <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/80 p-4">
                              <div className="flex flex-wrap gap-3 text-xs text-slate-400">
                                <span>Updated: {worker.updated_at ?? "n/a"}</span>
                                <span>Lineage: {short(worker.lineage_id ?? undefined)}</span>
                                <span>
                                  Parent:{" "}
                                  {worker.parent_worker_id ? short(worker.parent_worker_id) : "root"}
                                </span>
                                <span>Depth: {worker.spawn_depth ?? 0}</span>
                              </div>

                              {worker.summary ? (
                                <div className="space-y-1">
                                  <div className="text-xs uppercase tracking-[0.2em] text-cyan-300">Summary</div>
                                  <div className="rounded-lg border border-cyan-950/80 bg-cyan-950/20 p-3 text-sm text-slate-100">
                                    {worker.summary}
                                  </div>
                                </div>
                              ) : null}

                              {worker.error ? (
                                <div className="space-y-1">
                                  <div className="text-xs uppercase tracking-[0.2em] text-rose-300">Error</div>
                                  <div className="rounded-lg border border-rose-950/80 bg-rose-950/20 p-3 text-sm text-rose-100">
                                    {worker.error}
                                  </div>
                                </div>
                              ) : null}

                              {worker.output ? (
                                <div className="space-y-1">
                                  <div className="text-xs uppercase tracking-[0.2em] text-emerald-300">Output</div>
                                  <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900 p-3 text-xs text-slate-200">
                                    {JSON.stringify(worker.output, null, 2)}
                                  </pre>
                                </div>
                              ) : null}

                              {worker.tools_used && worker.tools_used.length > 0 ? (
                                <div className="space-y-1">
                                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Tools</div>
                                  <div className="text-sm text-slate-300">{worker.tools_used.join(", ")}</div>
                                </div>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ) : null,
                    ];
                  })}
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
