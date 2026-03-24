import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { fetchOcto } from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";
import { formatLocalDateTime } from "../utils/dateTime";

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
  telegram_send_tasks?: number;
  telegram_queues?: number;
  whatsapp_connected?: number;
  whatsapp_mapped_chats?: number;
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
    return (
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-slate-300">
        <h2 className="text-2xl font-semibold text-slate-100">Octo</h2>
        <p className="mt-2">Loading Octo operational state...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-2xl border border-rose-500/40 bg-rose-950/30 p-8 text-rose-200">
        <h2 className="text-2xl font-semibold text-rose-100">Octo</h2>
        <p className="mt-2">Failed to load octo telemetry: {error}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-8 text-slate-300">
        <h2 className="text-2xl font-semibold text-slate-100">Octo</h2>
        <p className="mt-2">No data returned.</p>
      </section>
    );
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
    <section className="grid gap-5">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/60">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Octo</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-100">
              {health.summary ?? "Orchestration core"}
            </h2>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              {(health.reasons ?? []).join(" | ") || "No active degradation reasons."}
            </p>
          </div>
          <div className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusTone(octo.state)}`}>
            {String(octo.state ?? "unknown")}
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Followup queues</p>
          <p className="mt-2 text-2xl font-semibold text-slate-100">{metric(octo.followup_queues)}</p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Internal queues</p>
          <p className="mt-2 text-2xl font-semibold text-slate-100">{metric(octo.internal_queues)}</p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Followup tasks</p>
          <p className="mt-2 text-2xl font-semibold text-slate-100">{metric(octo.followup_tasks)}</p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Internal tasks</p>
          <p className="mt-2 text-2xl font-semibold text-slate-100">{metric(octo.internal_tasks)}</p>
        </article>
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <article className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl shadow-slate-950/60">
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-300">Queues and Sessions</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                {isWhatsApp ? `${activeChannelLabel} bridge` : `${activeChannelLabel} queues`}
              </div>
              <div className="mt-2 text-xl font-semibold text-slate-100">
                {isWhatsApp ? (Number(queues.channel_connected ?? 0) > 0 ? "Connected" : "Disconnected") : metric(queues.channel_queue_depth)}
              </div>
              {channelUpdatedAt ? (
                <div className="mt-2 text-xs text-slate-500">Updated {formatLocalDateTime(channelUpdatedAt)}</div>
              ) : null}
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                {isWhatsApp ? "Mapped chats" : `${activeChannelLabel} send tasks`}
              </div>
              <div className="mt-2 text-xl font-semibold text-slate-100">
                {isWhatsApp ? metric(queues.channel_chat_mappings) : metric(queues.channel_send_tasks)}
              </div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">Exec sessions running</div>
              <div className="mt-2 text-xl font-semibold text-slate-100">{metric(queues.exec_sessions_running)}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">Exec sessions total</div>
              <div className="mt-2 text-xl font-semibold text-slate-100">{metric(queues.exec_sessions_total)}</div>
            </div>
          </div>
        </article>

        <article className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl shadow-slate-950/60">
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-300">Control Channel</h3>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">Pending requests</div>
              <div className="mt-2 text-xl font-semibold text-slate-100">{metric(control.pending_requests)}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">Last ack request</div>
              <div className="mt-2 text-sm font-medium text-slate-200">{metric(lastAck.request_id)}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">Last ack status</div>
              <div className={`mt-2 inline-flex rounded-full border px-2.5 py-1 text-xs uppercase tracking-wide ${statusTone(lastAck.status)}`}>
                {metric(lastAck.status)}
              </div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">Last ack timestamp</div>
              <div className="mt-2 text-sm font-medium text-slate-200">{formatLocalDateTime(lastAck.timestamp)}</div>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
