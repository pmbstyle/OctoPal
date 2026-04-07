import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchOcto } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";
import { formatLocalDateTime } from "../utils/dateTime";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type OctoPayload = components["schemas"]["DashboardOctoV2"];
type OctoView = {
  state?: string;
  followup_queues?: number;
  internal_queues?: number;
  followup_tasks?: number;
  internal_tasks?: number;
};
type QueuesView = {
  active_channel?: string;
  active_channel_label?: string;
  active_channel_updated_at?: string;
  channel_queue_depth?: number;
  channel_send_tasks?: number | null;
  channel_connected?: number | null;
  channel_chat_mappings?: number | null;
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

function statusTone(value?: string): string {
  const v = String(value ?? "").toLowerCase();
  if (v === "ok" || v === "idle") {
    return "border-emerald-400/30 bg-emerald-500/10 text-emerald-300";
  }
  if (v === "warning" || v === "thinking") {
    return "border-amber-300/30 bg-amber-500/10 text-amber-300";
  }
  return "border-rose-300/30 bg-rose-500/10 text-rose-300";
}

function metric(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  return String(value);
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

function MetricCard({ label, value, helper }: { label: string; value: string; helper?: string }) {
  return (
    <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] px-4 py-4">
      <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">{label}</p>
      <p className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">{value}</p>
      {helper ? <p className="mt-2 text-sm text-[var(--text-muted)]">{helper}</p> : null}
    </div>
  );
}

export function OctoPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<OctoPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");

    void fetchOcto({
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
    return <EmptyState title="Octo" message="Loading orchestration state..." />;
  }

  if (error) {
    return <EmptyState title="Octo" message={`Failed to load octo telemetry: ${error}`} tone="error" />;
  }

  if (!data) {
    return <EmptyState title="Octo" message="No data returned." />;
  }

  const octo = (data.octo ?? {}) as OctoView;
  const queues = (data.queues ?? {}) as QueuesView;
  const control = (data.control ?? {}) as ControlView;
  const health = (data.health ?? {}) as HealthView;
  const lastAck = control.last_ack ?? {};
  const activeChannel = String(queues.active_channel ?? "telegram").toLowerCase();
  const activeChannelLabel = String(queues.active_channel_label ?? (activeChannel === "whatsapp" ? "WhatsApp" : "Telegram"));
  const channelUpdatedAt = queues.active_channel_updated_at;
  const isWhatsApp = activeChannel === "whatsapp";

  return (
    <section className="grid gap-6">
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <Card className="rounded-[32px] border-white/6 bg-[var(--surface-panel)] py-0 shadow-[0_24px_80px_rgba(0,0,0,0.26)]">
          <CardContent className="px-6 py-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-3xl">
                <p className="text-[11px] uppercase tracking-[0.24em] text-[var(--text-dim)]">Octo runtime</p>
                <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">
                  {health.summary ?? "Orchestration core"}
                </h2>
                <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">
                  {(health.reasons ?? []).join(" | ") || "No active degradation reasons."}
                </p>
              </div>
              <Badge variant="outline" className={`rounded-full px-3 py-1.5 text-[11px] uppercase tracking-[0.18em] ${statusTone(octo.state)}`}>
                {String(octo.state ?? "unknown")}
              </Badge>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="Follow-up queues" value={metric(octo.followup_queues)} />
              <MetricCard label="Internal queues" value={metric(octo.internal_queues)} />
              <MetricCard label="Follow-up tasks" value={metric(octo.followup_tasks)} />
              <MetricCard label="Internal tasks" value={metric(octo.internal_tasks)} />
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[32px] border-white/6 bg-[var(--surface-panel)] py-0 shadow-[0_24px_80px_rgba(0,0,0,0.26)]">
          <CardHeader className="px-6 py-6">
            <CardTitle className="text-sm uppercase tracking-[0.18em] text-[var(--text-strong)]">Control lane</CardTitle>
            <CardDescription>Queue and acknowledgement state for operator-triggered requests.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 px-6 pb-6 pt-0">
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Pending requests</p>
              <p className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-white">{metric(control.pending_requests)}</p>
            </div>
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Last ack</p>
              <p className="mt-3 text-sm font-medium text-white">{metric(lastAck.request_id)}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline" className={`rounded-full ${statusTone(lastAck.status)}`}>
                  {metric(lastAck.status)}
                </Badge>
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  {formatLocalDateTime(lastAck.timestamp)}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Card className="rounded-[30px] border-white/6 bg-[var(--surface-panel)] py-0">
          <CardHeader className="px-6 py-5">
            <CardTitle className="text-sm uppercase tracking-[0.18em] text-[var(--text-strong)]">Queues and sessions</CardTitle>
            <CardDescription>Runtime pressure on the active user channel and exec sessions.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 px-6 pb-6 pt-0 sm:grid-cols-2">
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">
                {isWhatsApp ? `${activeChannelLabel} bridge` : `${activeChannelLabel} queue`}
              </div>
              <div className="mt-3 text-xl font-semibold text-white">
                {isWhatsApp ? (Number(queues.channel_connected ?? 0) > 0 ? "Connected" : "Disconnected") : metric(queues.channel_queue_depth)}
              </div>
              {channelUpdatedAt ? <div className="mt-2 text-xs text-[var(--text-muted)]">Updated {formatLocalDateTime(channelUpdatedAt)}</div> : null}
            </div>
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">
                {isWhatsApp ? "Mapped chats" : `${activeChannelLabel} send tasks`}
              </div>
              <div className="mt-3 text-xl font-semibold text-white">
                {isWhatsApp ? metric(queues.channel_chat_mappings) : metric(queues.channel_send_tasks)}
              </div>
            </div>
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Exec sessions running</div>
              <div className="mt-3 text-xl font-semibold text-white">{metric(queues.exec_sessions_running)}</div>
            </div>
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Exec sessions total</div>
              <div className="mt-3 text-xl font-semibold text-white">{metric(queues.exec_sessions_total)}</div>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[30px] border-white/6 bg-[var(--surface-panel)] py-0">
          <CardHeader className="px-6 py-5">
            <CardTitle className="text-sm uppercase tracking-[0.18em] text-[var(--text-strong)]">Channel context</CardTitle>
            <CardDescription>Quick read on where Octo is currently anchored.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 px-6 pb-6 pt-0">
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Active channel</p>
              <p className="mt-3 text-xl font-semibold text-white">{activeChannelLabel}</p>
            </div>
            <div className="rounded-[24px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Connected state</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline" className={`rounded-full ${statusTone(octo.state)}`}>
                  Octo {metric(octo.state)}
                </Badge>
                <Badge variant="outline" className="rounded-full border-white/8 bg-white/[0.04] text-[var(--text-muted)]">
                  {isWhatsApp ? `${metric(queues.channel_connected)} bridge online` : `${metric(queues.channel_queue_depth)} queued`}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </section>
  );
}
