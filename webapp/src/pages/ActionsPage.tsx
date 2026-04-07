import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchActions, runDashboardAction } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";
import { formatLocalDateTime } from "../utils/dateTime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type ActionsPayload = components["schemas"]["DashboardActionsV2"];
type ActionHistoryItem = {
  timestamp?: string;
  action?: string;
  requested_by?: string;
  worker_id?: string;
  result?: { status?: string; message?: string };
};

function statusTone(value?: string): string {
  const v = String(value ?? "").toLowerCase();
  if (v === "ok") {
    return "border-emerald-400/30 bg-emerald-500/10 text-emerald-300";
  }
  if (v === "warning") {
    return "border-amber-300/30 bg-amber-500/10 text-amber-300";
  }
  return "border-rose-300/30 bg-rose-500/10 text-rose-300";
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
    <section className="grid gap-6">
      <Card className="rounded-[32px] border-white/6 bg-[var(--surface-panel)] py-0 shadow-[0_24px_80px_rgba(0,0,0,0.24)]">
        <CardContent className="px-6 py-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <p className="text-[11px] uppercase tracking-[0.24em] text-[var(--text-dim)]">Actions</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">Operational controls</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">
                Manual recovery actions for worker restarts and queue cleanup, with backend audit history below.
              </p>
            </div>
            <Badge variant="outline" className={`rounded-full px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] ${error ? statusTone("error") : statusTone("ok")}`}>
              {error ? "load error" : "ready"}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
        <Card className="rounded-[30px] border-white/6 bg-[var(--surface-panel)] py-0">
          <CardHeader className="px-6 py-5">
            <CardTitle className="text-sm uppercase tracking-[0.18em] text-[var(--text-strong)]">Run action</CardTitle>
            <CardDescription>Use this panel for targeted recovery when automation did not cleanly resolve an issue.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 px-6 pb-6 pt-0">
            <form onSubmit={onRestartSubmit} className="space-y-3">
              <label className="grid gap-2">
                <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Worker ID</span>
                <Input
                  value={workerId}
                  onChange={(event) => setWorkerId(event.target.value)}
                  placeholder="Worker ID"
                  aria-label="Worker ID"
                  className="rounded-[18px] border-white/8 bg-[var(--surface-panel-strong)]"
                />
              </label>
              <Button
                type="submit"
                className="w-full rounded-[18px] bg-white/[0.08] text-white hover:bg-white/[0.12]"
              >
                Restart worker
              </Button>
            </form>

            <div className="grid gap-3">
              <Button
                type="button"
                variant="secondary"
                className="rounded-[18px] bg-[var(--surface-panel-strong)] text-[var(--text-strong)] hover:bg-white/[0.08]"
                onClick={() => void runAction("retry_failed")}
              >
                Retry latest failed worker
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="rounded-[18px] bg-[var(--surface-panel-strong)] text-[var(--text-strong)] hover:bg-white/[0.08]"
                onClick={() => void runAction("clear_control_queue")}
              >
                Clear control queue
              </Button>
            </div>

            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Result</div>
              <p className="mt-3 text-sm text-[var(--text-strong)]">{resultMessage}</p>
              {error ? <p className="mt-2 text-sm text-rose-300">Load error: {error}</p> : null}
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[30px] border-white/6 bg-[var(--surface-panel)] py-0">
          <CardHeader className="flex-row items-center justify-between gap-3 px-6 py-5">
            <div>
              <CardTitle className="text-sm uppercase tracking-[0.18em] text-[var(--text-strong)]">Action history</CardTitle>
              <CardDescription>Latest backend audit entries for dashboard-triggered actions.</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="px-6 pb-6 pt-0">
            {loading ? (
              <p className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-[var(--text-muted)]">Loading history...</p>
            ) : history.length === 0 ? (
              <p className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-[var(--text-muted)]">No action history.</p>
            ) : (
              <div className="overflow-x-auto rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)]">
                <Table className="min-w-[720px]">
                  <TableHeader>
                    <TableRow className="border-white/6 hover:bg-transparent">
                      <TableHead>Time</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead>Requester</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Message</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.slice(0, 12).map((item, index) => (
                      <TableRow key={`${item.timestamp ?? "n/a"}-${index}`} className="border-white/6 hover:bg-white/[0.02]">
                        <TableCell className="text-[var(--text-muted)]">{formatLocalDateTime(item.timestamp)}</TableCell>
                        <TableCell className="text-[var(--text-strong)]">
                          {item.action ?? "action"}
                          {item.worker_id ? ` (${item.worker_id})` : ""}
                        </TableCell>
                        <TableCell className="text-[var(--text-muted)]">{item.requested_by ?? "dashboard"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={`rounded-full ${statusTone(item.result?.status)}`}>
                            {String(item.result?.status ?? "unknown")}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-[var(--text-strong)]">{item.result?.message ?? "n/a"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
