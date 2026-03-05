import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchActions, runDashboardAction } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";

type ActionsPayload = components["schemas"]["DashboardActionsV2"];
type ActionHistoryItem = {
  timestamp?: string;
  action?: string;
  requested_by?: string;
  worker_id?: string;
  result?: { status?: string; message?: string };
};

function tone(value?: string): string {
  const v = String(value ?? "").toLowerCase();
  if (v === "ok") {
    return "tone-ok";
  }
  if (v === "warning") {
    return "tone-warn";
  }
  return "tone-bad";
}

export function ActionsPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<ActionsPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [workerId, setWorkerId] = useState<string>("");
  const [resultMessage, setResultMessage] = useState<string>("No actions yet.");

  const loadActions = () => {
    setLoading(true);
    setError("");
    void fetchActions({
      windowMinutes: filters.windowMinutes,
      service: filters.service,
      environment: filters.environment,
      token: filters.token || undefined,
    })
      .then((payload) => {
        setData(payload);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Unknown request error");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadActions();
  }, [filters.environment, filters.service, filters.token, filters.windowMinutes]);

  const runAction = async (action: "restart_worker" | "retry_failed" | "clear_control_queue") => {
    try {
      setResultMessage("Running action...");
      const payload =
        action === "restart_worker"
          ? { action, worker_id: workerId.trim(), confirm: true }
          : action === "clear_control_queue"
            ? { action, confirm: true }
            : { action };
      const response = await runDashboardAction(payload, filters.token || undefined);
      setResultMessage(String(response.message ?? response.status ?? "Action completed."));
      loadActions();
    } catch (err: unknown) {
      setResultMessage(err instanceof Error ? err.message : "Action failed.");
    }
  };

  const onRestartSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!workerId.trim()) {
      setResultMessage("Enter worker ID before restart.");
      return;
    }
    void runAction("restart_worker");
  };

  const actionsNode = (data?.actions ?? {}) as { history?: ActionHistoryItem[] };
  const history = actionsNode.history ?? [];

  return (
    <section className="panel">
      <h2>Actions</h2>
      <p className="overview-meta">Operational controls with backend audit trail.</p>

      <div className="overview-columns">
        <article className="mini-panel">
          <h4>Run Action</h4>
          <form onSubmit={onRestartSubmit} className="action-form">
            <input
              value={workerId}
              onChange={(event) => setWorkerId(event.target.value)}
              placeholder="Worker ID"
              aria-label="Worker ID"
            />
            <button type="submit" className="drill-btn">
              Restart Worker
            </button>
          </form>
          <div className="action-row">
            <button type="button" className="drill-btn" onClick={() => void runAction("retry_failed")}>
              Retry Latest Failed
            </button>
            <button type="button" className="drill-btn" onClick={() => void runAction("clear_control_queue")}>
              Clear Control Queue
            </button>
          </div>
          <p>{resultMessage}</p>
          {error ? <p className="tone-bad">Load error: {error}</p> : null}
        </article>

        <article className="mini-panel">
          <h4>Action History</h4>
          {loading ? (
            <p>Loading history...</p>
          ) : history.length === 0 ? (
            <p>No action history.</p>
          ) : (
            <ul className="plain-list">
              {history.slice(0, 12).map((item, index) => (
                <li key={`${item.timestamp ?? "n/a"}-${index}`}>
                  <span className={tone(item.result?.status)}>{String(item.result?.status ?? "unknown").toUpperCase()}</span>{" "}
                  {item.action ?? "action"} by {item.requested_by ?? "dashboard"}
                  {item.worker_id ? ` (worker ${item.worker_id})` : ""} - {item.result?.message ?? "n/a"}
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>
    </section>
  );
}
