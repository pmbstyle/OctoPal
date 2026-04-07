import { useEffect, useState, type ReactNode } from "react";
import { useOutletContext } from "react-router-dom";

import {
  fetchDashboardConfig,
  fetchSystem,
  updateDashboardConfig,
  type DashboardConfigResponse,
  type DashboardEditableConfig,
} from "../api/dashboardClient";
import type { components } from "../api/types";
import type { AppShellOutletContext } from "../ui/AppShell";
import { formatLocalDateTime } from "../utils/dateTime";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type SystemPayload = components["schemas"]["DashboardSystemV2"];
type ServiceItem = { id?: string; name?: string; status?: string; reason?: string; updated_at?: string };
type LogItem = { timestamp?: string; level?: string; event?: string; service?: string };
type Connectivity = {
  mcp_servers?: Record<string, { status?: string; tool_count?: number; name?: string; reason?: string; transport?: string; reconnect_attempts?: number; error?: string | null }>;
};

type FormState = {
  user_channel: string;
  log_level: string;
  debug_prompts: boolean;
  heartbeat_interval_seconds: string;
  user_message_grace_seconds: string;
  state_dir: string;
  workspace_dir: string;
  memory_top_k: string;
  memory_prefilter_k: string;
  memory_min_score: string;
  memory_max_chars: string;
  memory_owner_id: string;
  gateway_host: string;
  gateway_port: string;
  gateway_tailscale_ips: string;
  gateway_dashboard_token: string;
  gateway_tailscale_auto_serve: boolean;
  gateway_webapp_enabled: boolean;
  gateway_webapp_dist_dir: string;
  workers_launcher: string;
  workers_docker_image: string;
  workers_docker_workspace: string;
  workers_docker_host_workspace: string;
  workers_max_spawn_depth: string;
  workers_max_children_total: string;
  workers_max_children_concurrent: string;
  telegram_bot_token: string;
  telegram_allowed_chat_ids: string;
  telegram_parse_mode: string;
  whatsapp_mode: string;
  whatsapp_allowed_numbers: string;
  whatsapp_auth_dir: string;
  whatsapp_bridge_host: string;
  whatsapp_bridge_port: string;
  whatsapp_callback_token: string;
  whatsapp_node_command: string;
  llm_provider_id: string;
  llm_model: string;
  llm_api_key: string;
  llm_api_base: string;
  llm_model_prefix: string;
  worker_llm_provider_id: string;
  worker_llm_model: string;
  worker_llm_api_key: string;
  worker_llm_api_base: string;
  worker_llm_model_prefix: string;
  litellm_num_retries: string;
  litellm_timeout: string;
  litellm_fallbacks: string;
  litellm_drop_params: boolean;
  litellm_caching: boolean;
  litellm_max_concurrency: string;
  litellm_rate_limit_max_retries: string;
  litellm_rate_limit_base_delay_seconds: string;
  litellm_rate_limit_max_delay_seconds: string;
  search_brave_api_key: string;
  search_firecrawl_api_key: string;
};

const panel = "rounded-[30px] border border-white/6 bg-[var(--surface-panel)] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.26)]";
const inputClass = "h-10 rounded-[18px] border-white/8 bg-[var(--surface-panel-strong)] px-3 text-[var(--text-strong)] placeholder:text-[var(--text-dim)]";
const textareaClass = "rounded-[18px] border-white/8 bg-[var(--surface-panel-strong)] px-3 py-2.5 text-[var(--text-strong)] placeholder:text-[var(--text-dim)]";
const selectTriggerClass = "h-10 w-full rounded-[18px] border-white/8 bg-[var(--surface-panel-strong)] px-3 text-[var(--text-strong)]";

function statusTone(status?: string): string {
  const v = String(status ?? "").toLowerCase();
  if (v === "ok" || v === "connected" || v === "running") return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  if (v === "warning" || v === "reconnecting" || v === "configured") return "border-amber-300/20 bg-amber-300/10 text-amber-100";
  return "border-rose-300/20 bg-rose-400/10 text-rose-100";
}

const listToText = (value: string[]) => value.join("\n");
const parseList = (value: string) => value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
const maybe = (value: string) => (value.trim() ? value.trim() : null);

function buildForm(config: DashboardEditableConfig): FormState {
  return {
    user_channel: config.user_channel,
    log_level: config.log_level,
    debug_prompts: config.debug_prompts,
    heartbeat_interval_seconds: String(config.heartbeat_interval_seconds),
    user_message_grace_seconds: String(config.user_message_grace_seconds),
    state_dir: config.storage.state_dir,
    workspace_dir: config.storage.workspace_dir,
    memory_top_k: String(config.memory.top_k),
    memory_prefilter_k: String(config.memory.prefilter_k),
    memory_min_score: String(config.memory.min_score),
    memory_max_chars: String(config.memory.max_chars),
    memory_owner_id: config.memory.owner_id,
    gateway_host: config.gateway.host,
    gateway_port: String(config.gateway.port),
    gateway_tailscale_ips: config.gateway.tailscale_ips,
    gateway_dashboard_token: config.gateway.dashboard_token,
    gateway_tailscale_auto_serve: config.gateway.tailscale_auto_serve,
    gateway_webapp_enabled: config.gateway.webapp_enabled,
    gateway_webapp_dist_dir: config.gateway.webapp_dist_dir ?? "",
    workers_launcher: config.workers.launcher,
    workers_docker_image: config.workers.docker_image,
    workers_docker_workspace: config.workers.docker_workspace,
    workers_docker_host_workspace: config.workers.docker_host_workspace ?? "",
    workers_max_spawn_depth: String(config.workers.max_spawn_depth),
    workers_max_children_total: String(config.workers.max_children_total),
    workers_max_children_concurrent: String(config.workers.max_children_concurrent),
    telegram_bot_token: config.telegram.bot_token,
    telegram_allowed_chat_ids: listToText(config.telegram.allowed_chat_ids),
    telegram_parse_mode: config.telegram.parse_mode,
    whatsapp_mode: config.whatsapp.mode,
    whatsapp_allowed_numbers: listToText(config.whatsapp.allowed_numbers),
    whatsapp_auth_dir: config.whatsapp.auth_dir ?? "",
    whatsapp_bridge_host: config.whatsapp.bridge_host,
    whatsapp_bridge_port: String(config.whatsapp.bridge_port),
    whatsapp_callback_token: config.whatsapp.callback_token,
    whatsapp_node_command: config.whatsapp.node_command,
    llm_provider_id: config.llm.provider_id ?? "",
    llm_model: config.llm.model ?? "",
    llm_api_key: config.llm.api_key ?? "",
    llm_api_base: config.llm.api_base ?? "",
    llm_model_prefix: config.llm.model_prefix ?? "",
    worker_llm_provider_id: config.worker_llm_default.provider_id ?? "",
    worker_llm_model: config.worker_llm_default.model ?? "",
    worker_llm_api_key: config.worker_llm_default.api_key ?? "",
    worker_llm_api_base: config.worker_llm_default.api_base ?? "",
    worker_llm_model_prefix: config.worker_llm_default.model_prefix ?? "",
    litellm_num_retries: String(config.litellm.num_retries),
    litellm_timeout: String(config.litellm.timeout),
    litellm_fallbacks: config.litellm.fallbacks ?? "",
    litellm_drop_params: config.litellm.drop_params,
    litellm_caching: config.litellm.caching,
    litellm_max_concurrency: String(config.litellm.max_concurrency),
    litellm_rate_limit_max_retries: String(config.litellm.rate_limit_max_retries),
    litellm_rate_limit_base_delay_seconds: String(config.litellm.rate_limit_base_delay_seconds),
    litellm_rate_limit_max_delay_seconds: String(config.litellm.rate_limit_max_delay_seconds),
    search_brave_api_key: config.search.brave_api_key ?? "",
    search_firecrawl_api_key: config.search.firecrawl_api_key ?? "",
  };
}

function toPayload(form: FormState): DashboardEditableConfig {
  return {
    user_channel: form.user_channel,
    telegram: { bot_token: form.telegram_bot_token.trim(), allowed_chat_ids: parseList(form.telegram_allowed_chat_ids), parse_mode: form.telegram_parse_mode.trim() || "MarkdownV2" },
    llm: { provider_id: maybe(form.llm_provider_id), model: maybe(form.llm_model), api_key: maybe(form.llm_api_key), api_base: maybe(form.llm_api_base), model_prefix: maybe(form.llm_model_prefix) },
    worker_llm_default: { provider_id: maybe(form.worker_llm_provider_id), model: maybe(form.worker_llm_model), api_key: maybe(form.worker_llm_api_key), api_base: maybe(form.worker_llm_api_base), model_prefix: maybe(form.worker_llm_model_prefix) },
    litellm: { num_retries: Number(form.litellm_num_retries || 0), timeout: Number(form.litellm_timeout || 0), fallbacks: maybe(form.litellm_fallbacks), drop_params: form.litellm_drop_params, caching: form.litellm_caching, max_concurrency: Number(form.litellm_max_concurrency || 0), rate_limit_max_retries: Number(form.litellm_rate_limit_max_retries || 0), rate_limit_base_delay_seconds: Number(form.litellm_rate_limit_base_delay_seconds || 0), rate_limit_max_delay_seconds: Number(form.litellm_rate_limit_max_delay_seconds || 0) },
    storage: { state_dir: form.state_dir.trim(), workspace_dir: form.workspace_dir.trim() },
    memory: { top_k: Number(form.memory_top_k || 0), prefilter_k: Number(form.memory_prefilter_k || 0), min_score: Number(form.memory_min_score || 0), max_chars: Number(form.memory_max_chars || 0), owner_id: form.memory_owner_id.trim() },
    gateway: { host: form.gateway_host.trim(), port: Number(form.gateway_port || 0), tailscale_ips: form.gateway_tailscale_ips.trim(), dashboard_token: form.gateway_dashboard_token.trim(), tailscale_auto_serve: form.gateway_tailscale_auto_serve, webapp_enabled: form.gateway_webapp_enabled, webapp_dist_dir: maybe(form.gateway_webapp_dist_dir) },
    workers: { launcher: form.workers_launcher.trim(), docker_image: form.workers_docker_image.trim(), docker_workspace: form.workers_docker_workspace.trim(), docker_host_workspace: maybe(form.workers_docker_host_workspace), max_spawn_depth: Number(form.workers_max_spawn_depth || 0), max_children_total: Number(form.workers_max_children_total || 0), max_children_concurrent: Number(form.workers_max_children_concurrent || 0) },
    whatsapp: { mode: form.whatsapp_mode.trim(), allowed_numbers: parseList(form.whatsapp_allowed_numbers), auth_dir: maybe(form.whatsapp_auth_dir), bridge_host: form.whatsapp_bridge_host.trim(), bridge_port: Number(form.whatsapp_bridge_port || 0), callback_token: form.whatsapp_callback_token.trim(), node_command: form.whatsapp_node_command.trim() },
    search: { brave_api_key: maybe(form.search_brave_api_key), firecrawl_api_key: maybe(form.search_firecrawl_api_key) },
    log_level: form.log_level,
    debug_prompts: form.debug_prompts,
    heartbeat_interval_seconds: Number(form.heartbeat_interval_seconds || 0),
    user_message_grace_seconds: Number(form.user_message_grace_seconds || 0),
  };
}

function L({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-1.5 text-sm text-[var(--text-strong)]"><span className="text-[11px] uppercase tracking-[0.18em] text-white/92">{label}</span>{children}</label>;
}

function H({ title, text }: { title: string; text: string }) {
  return <div className="mb-4"><p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">{title}</p><p className="mt-2 text-sm text-[var(--text-muted)]">{text}</p></div>;
}

function FormInput(props: React.ComponentProps<typeof Input>) {
  return <Input {...props} className={[inputClass, props.className].filter(Boolean).join(" ")} />;
}

function FormTextarea(props: React.ComponentProps<typeof Textarea>) {
  return <Textarea {...props} className={[textareaClass, props.className].filter(Boolean).join(" ")} />;
}

function FormSelect({
  value,
  onValueChange,
  options,
  placeholder,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  placeholder?: string;
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className={selectTriggerClass}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function ToggleField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-3 rounded-[18px] border border-white/6 bg-[var(--surface-panel-strong)] px-3 py-3 text-sm text-[var(--text-strong)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-white/20 bg-transparent"
      />
      {label}
    </label>
  );
}

export function SystemPage() {
  const { filters } = useOutletContext<AppShellOutletContext>();
  const [data, setData] = useState<SystemPayload | null>(null);
  const [configData, setConfigData] = useState<DashboardConfigResponse | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [configLoading, setConfigLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [configError, setConfigError] = useState("");
  const [notice, setNotice] = useState("");

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
        if (active) setData(payload);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Unknown request error");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters.environment, filters.service, filters.token, filters.windowMinutes]);

  useEffect(() => {
    let active = true;
    setConfigLoading(true);
    setConfigError("");
    void fetchDashboardConfig(filters.token || undefined)
      .then((payload) => {
        if (!active) return;
        setConfigData(payload);
        setForm(buildForm(payload.config));
      })
      .catch((err: unknown) => {
        if (active) setConfigError(err instanceof Error ? err.message : "Failed to load config");
      })
      .finally(() => {
        if (active) setConfigLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters.token]);

  if (loading) {
    return <section className={panel}><h2 className="text-2xl font-semibold text-white">System</h2><p className="mt-2 text-sm text-[var(--text-muted)]">Loading system diagnostics...</p></section>;
  }

  if (error) {
    return <section className="rounded-[30px] border border-rose-400/30 bg-rose-950/20 p-8 text-rose-100"><h2 className="text-2xl font-semibold text-white">System</h2><p className="mt-2 text-sm">Failed to load system diagnostics: {error}</p></section>;
  }

  const system = (data?.system ?? {}) as { running?: boolean; pid?: number; uptime?: string; active_channel?: string; worker_launcher?: { configured?: string; effective?: string; available?: boolean; reason?: string } };
  const services = ((data?.services ?? []) as ServiceItem[]).slice(0, 10);
  const logs = ((data?.logs ?? []) as LogItem[]).slice(0, 10);
  const connectivity = (data?.connectivity ?? {}) as Connectivity;
  const mcpServers = connectivity.mcp_servers ?? {};
  const launcher = configData?.worker_launcher ?? { configured: "n/a", effective: "n/a", available: false, reason: "No data", docker_image: "n/a" };
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((current) => (current ? { ...current, [key]: value } : current));

  async function save(): Promise<void> {
    if (!form) return;
    setSaving(true);
    setNotice("");
    setConfigError("");
    try {
      const payload = await updateDashboardConfig(toPayload(form), filters.token || undefined);
      setConfigData((current) => ({ config: payload.config, worker_launcher: payload.worker_launcher, notes: current?.notes ?? [] }));
      setForm(buildForm(payload.config));
      setNotice("Config saved to config.json.");
    } catch (err: unknown) {
      setConfigError(err instanceof Error ? err.message : "Failed to save config");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="grid gap-5">
      <section className={panel}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">System</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-white">{system.running ? "Runtime is healthy" : "Runtime is degraded"}</h2>
            <p className="mt-3 text-sm text-[var(--text-muted)]">PID {system.pid ?? "n/a"} | Channel {system.active_channel ?? "n/a"} | Uptime {system.uptime ?? "n/a"}</p>
          </div>
          <div className={`rounded-full border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.16em] ${statusTone(system.running ? "running" : "critical")}`}>{system.running ? "running" : "down"}</div>
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-3">
        <article className={panel}>
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-strong)]">Service health</h3>
          <div className="mt-4 space-y-3">
            {services.length === 0 ? <p className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-sm text-[var(--text-muted)]">No services.</p> : services.map((service) => (
              <article key={service.id ?? service.name} className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div><h4 className="text-base font-semibold text-white">{service.name ?? "Service"}</h4><p className="mt-1 text-sm text-[var(--text-muted)]">{service.reason ?? "No reason"}</p></div>
                  <div className={`rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-wide ${statusTone(service.status)}`}>{String(service.status ?? "unknown")}</div>
                </div>
              </article>
            ))}
          </div>
        </article>

        <article className={panel}>
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-strong)]">MCP connectivity</h3>
          <div className="mt-4 space-y-3">
            {Object.keys(mcpServers).length === 0 ? <p className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-sm text-[var(--text-muted)]">No MCP servers configured.</p> : Object.entries(mcpServers).map(([key, value]) => (
              <article key={key} className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h4 className="text-base font-semibold text-white">{value.name ?? key}</h4>
                    <p className="mt-1 text-sm text-[var(--text-muted)]">Available tools: {value.tool_count ?? 0} | Transport: {value.transport ?? "auto"}</p>
                    <p className="mt-1 text-sm text-[var(--text-dim)]">{value.reason ?? "No detail available"}{typeof value.reconnect_attempts === "number" && value.reconnect_attempts > 0 ? ` | Retry attempts: ${value.reconnect_attempts}` : ""}</p>
                    {value.error ? <p className="mt-1 text-sm text-rose-200">{value.error}</p> : null}
                  </div>
                  <div className={`rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-wide ${statusTone(value.status)}`}>{String(value.status ?? "unknown")}</div>
                </div>
              </article>
            ))}
          </div>
        </article>

        <article className={panel}>
          <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-strong)]">Launcher status</h3>
          <div className="mt-4 space-y-3">
            <div className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4"><div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Configured</div><div className="mt-2 text-lg font-semibold text-white">{launcher.configured}</div></div>
            <div className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4"><div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Effective</div><div className="mt-2 text-lg font-semibold text-white">{launcher.effective}</div></div>
            <div className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4"><div className="flex items-center justify-between gap-3"><div className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Availability</div><span className={`rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-wide ${statusTone(launcher.available ? "running" : "warning")}`}>{launcher.available ? "ready" : "needs attention"}</span></div><p className="mt-3 text-sm text-[var(--text-muted)]">{launcher.reason}</p></div>
          </div>
        </article>
      </div>

      <article className={panel}>
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/6 pb-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-dim)]">Config editor</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">Edit `config.json` from the dashboard</h3>
            <p className="mt-2 max-w-3xl text-sm text-[var(--text-muted)]">This form writes the structured runtime config back to disk. Some changes apply fully after restart.</p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => { if (configData) { setForm(buildForm(configData.config)); setNotice(""); setConfigError(""); } }} disabled={!form || configLoading || saving} className="rounded-2xl border-white/8 bg-transparent text-[var(--text-muted)] hover:bg-white/[0.04] hover:text-[var(--text-strong)]">
              Reset
            </Button>
            <Button type="button" variant="secondary" onClick={() => void save()} disabled={!form || configLoading || saving} className="rounded-2xl bg-white/[0.08] text-[var(--text-strong)] hover:bg-white/[0.12]">
              {saving ? "Saving..." : "Save config"}
            </Button>
          </div>
        </div>

        {configLoading ? <p className="mt-5 text-sm text-[var(--text-muted)]">Loading structured config...</p> : null}
        {configError ? <div className="mt-5 rounded-2xl border border-rose-400/30 bg-rose-950/20 p-4 text-sm text-rose-100">{configError}</div> : null}
        {notice ? <div className="mt-5 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm text-emerald-100">{notice}</div> : null}
        {configData?.notes?.length ? <div className="mt-5 grid gap-2">{configData.notes.map((note) => <div key={note} className="rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] px-4 py-3 text-sm text-[var(--text-muted)]">{note}</div>)}</div> : null}

        {form ? (
          <div className="mt-6 space-y-8">
            <section>
              <H title="General" text="Core runtime channel and behavior flags." />
              <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
                <L label="User channel"><FormSelect value={form.user_channel} onValueChange={(value) => set("user_channel", value)} options={[{ value: "telegram", label: "Telegram" }, { value: "whatsapp", label: "WhatsApp" }]} /></L>
                <L label="Log level"><FormSelect value={form.log_level} onValueChange={(value) => set("log_level", value)} options={[{ value: "DEBUG", label: "DEBUG" }, { value: "INFO", label: "INFO" }, { value: "WARNING", label: "WARNING" }, { value: "ERROR", label: "ERROR" }]} /></L>
                <L label="Heartbeat seconds"><FormInput value={form.heartbeat_interval_seconds} onChange={(e) => set("heartbeat_interval_seconds", e.target.value)} /></L>
                <L label="Grace seconds"><FormInput value={form.user_message_grace_seconds} onChange={(e) => set("user_message_grace_seconds", e.target.value)} /></L>
              </div>
              <div className="mt-4">
                <ToggleField label="Enable prompt debugging" checked={form.debug_prompts} onChange={(checked) => set("debug_prompts", checked)} />
              </div>
            </section>

            <section>
              <H title="Storage and memory" text="Workspace paths and retrieval tuning." />
              <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
                <L label="State dir"><FormInput value={form.state_dir} onChange={(e) => set("state_dir", e.target.value)} /></L>
                <L label="Workspace dir"><FormInput value={form.workspace_dir} onChange={(e) => set("workspace_dir", e.target.value)} /></L>
                <L label="Top k"><FormInput value={form.memory_top_k} onChange={(e) => set("memory_top_k", e.target.value)} /></L>
                <L label="Prefilter k"><FormInput value={form.memory_prefilter_k} onChange={(e) => set("memory_prefilter_k", e.target.value)} /></L>
                <L label="Min score"><FormInput value={form.memory_min_score} onChange={(e) => set("memory_min_score", e.target.value)} /></L>
                <L label="Max chars"><FormInput value={form.memory_max_chars} onChange={(e) => set("memory_max_chars", e.target.value)} /></L>
                <L label="Owner id"><FormInput value={form.memory_owner_id} onChange={(e) => set("memory_owner_id", e.target.value)} /></L>
              </div>
            </section>

            <section>
              <H title="Gateway and workers" text="Entry point, dashboard auth, webapp serving and worker launcher." />
              <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
                <L label="Gateway host"><FormInput value={form.gateway_host} onChange={(e) => set("gateway_host", e.target.value)} /></L>
                <L label="Gateway port"><FormInput value={form.gateway_port} onChange={(e) => set("gateway_port", e.target.value)} /></L>
                <L label="Tailscale IPs"><FormInput value={form.gateway_tailscale_ips} onChange={(e) => set("gateway_tailscale_ips", e.target.value)} /></L>
                <L label="Dashboard token"><FormInput type="password" value={form.gateway_dashboard_token} onChange={(e) => set("gateway_dashboard_token", e.target.value)} placeholder="Leave blank to keep current token" /></L>
                <L label="Webapp dist dir"><FormInput value={form.gateway_webapp_dist_dir} onChange={(e) => set("gateway_webapp_dist_dir", e.target.value)} /></L>
                <L label="Launcher"><FormSelect value={form.workers_launcher} onValueChange={(value) => set("workers_launcher", value)} options={[{ value: "docker", label: "Docker" }, { value: "same_env", label: "Same env" }]} /></L>
                <L label="Docker image"><FormInput value={form.workers_docker_image} onChange={(e) => set("workers_docker_image", e.target.value)} /></L>
                <L label="Docker workspace"><FormInput value={form.workers_docker_workspace} onChange={(e) => set("workers_docker_workspace", e.target.value)} /></L>
                <L label="Host workspace"><FormInput value={form.workers_docker_host_workspace} onChange={(e) => set("workers_docker_host_workspace", e.target.value)} /></L>
                <L label="Max spawn depth"><FormInput value={form.workers_max_spawn_depth} onChange={(e) => set("workers_max_spawn_depth", e.target.value)} /></L>
                <L label="Max children total"><FormInput value={form.workers_max_children_total} onChange={(e) => set("workers_max_children_total", e.target.value)} /></L>
                <L label="Max children concurrent"><FormInput value={form.workers_max_children_concurrent} onChange={(e) => set("workers_max_children_concurrent", e.target.value)} /></L>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <ToggleField label="Enable Tailscale auto serve" checked={form.gateway_tailscale_auto_serve} onChange={(checked) => set("gateway_tailscale_auto_serve", checked)} />
                <ToggleField label="Enable bundled webapp" checked={form.gateway_webapp_enabled} onChange={(checked) => set("gateway_webapp_enabled", checked)} />
              </div>
            </section>

            <section>
              <H title="Channels" text="Telegram and WhatsApp delivery settings." />
              <div className="grid gap-5 xl:grid-cols-2">
                <div className="space-y-4 rounded-[26px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                  <h4 className="text-base font-semibold text-white">Telegram</h4>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <L label="Bot token"><FormInput type="password" value={form.telegram_bot_token} onChange={(e) => set("telegram_bot_token", e.target.value)} placeholder="Leave blank to keep current token" /></L>
                    <L label="Parse mode"><FormInput value={form.telegram_parse_mode} onChange={(e) => set("telegram_parse_mode", e.target.value)} /></L>
                  </div>
                  <L label="Allowed chat IDs"><FormTextarea value={form.telegram_allowed_chat_ids} onChange={(e) => set("telegram_allowed_chat_ids", e.target.value)} rows={4} /></L>
                </div>

                <div className="space-y-4 rounded-[26px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                  <h4 className="text-base font-semibold text-white">WhatsApp</h4>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <L label="Mode"><FormSelect value={form.whatsapp_mode} onValueChange={(value) => set("whatsapp_mode", value)} options={[{ value: "separate", label: "Separate bridge" }, { value: "embedded", label: "Embedded" }]} /></L>
                    <L label="Auth dir"><FormInput value={form.whatsapp_auth_dir} onChange={(e) => set("whatsapp_auth_dir", e.target.value)} /></L>
                    <L label="Bridge host"><FormInput value={form.whatsapp_bridge_host} onChange={(e) => set("whatsapp_bridge_host", e.target.value)} /></L>
                    <L label="Bridge port"><FormInput value={form.whatsapp_bridge_port} onChange={(e) => set("whatsapp_bridge_port", e.target.value)} /></L>
                    <L label="Callback token"><FormInput type="password" value={form.whatsapp_callback_token} onChange={(e) => set("whatsapp_callback_token", e.target.value)} placeholder="Leave blank to keep current token" /></L>
                    <L label="Node command"><FormInput value={form.whatsapp_node_command} onChange={(e) => set("whatsapp_node_command", e.target.value)} /></L>
                  </div>
                  <L label="Allowed numbers"><FormTextarea value={form.whatsapp_allowed_numbers} onChange={(e) => set("whatsapp_allowed_numbers", e.target.value)} rows={4} /></L>
                </div>
              </div>
            </section>

            <section>
              <H title="LLM and search" text="Default model profiles, LiteLLM transport and external search providers." />
              <div className="grid gap-5 xl:grid-cols-2">
                <div className="space-y-4 rounded-[26px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                  <h4 className="text-base font-semibold text-white">Octo default</h4>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <L label="Provider ID"><FormInput value={form.llm_provider_id} onChange={(e) => set("llm_provider_id", e.target.value)} /></L>
                    <L label="Model"><FormInput value={form.llm_model} onChange={(e) => set("llm_model", e.target.value)} /></L>
                    <L label="API key"><FormInput type="password" value={form.llm_api_key} onChange={(e) => set("llm_api_key", e.target.value)} placeholder="Leave blank to keep current key" /></L>
                    <L label="API base"><FormInput value={form.llm_api_base} onChange={(e) => set("llm_api_base", e.target.value)} /></L>
                    <L label="Model prefix"><FormInput value={form.llm_model_prefix} onChange={(e) => set("llm_model_prefix", e.target.value)} /></L>
                  </div>
                </div>

                <div className="space-y-4 rounded-[26px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                  <h4 className="text-base font-semibold text-white">Worker default</h4>
                  <div className="grid gap-4 lg:grid-cols-2">
                    <L label="Provider ID"><FormInput value={form.worker_llm_provider_id} onChange={(e) => set("worker_llm_provider_id", e.target.value)} /></L>
                    <L label="Model"><FormInput value={form.worker_llm_model} onChange={(e) => set("worker_llm_model", e.target.value)} /></L>
                    <L label="API key"><FormInput type="password" value={form.worker_llm_api_key} onChange={(e) => set("worker_llm_api_key", e.target.value)} placeholder="Leave blank to keep current key" /></L>
                    <L label="API base"><FormInput value={form.worker_llm_api_base} onChange={(e) => set("worker_llm_api_base", e.target.value)} /></L>
                    <L label="Model prefix"><FormInput value={form.worker_llm_model_prefix} onChange={(e) => set("worker_llm_model_prefix", e.target.value)} /></L>
                  </div>
                </div>
              </div>

              <div className="mt-5 rounded-[26px] border border-white/6 bg-[var(--surface-panel-strong)] p-4">
                <h4 className="text-base font-semibold text-white">LiteLLM runtime</h4>
                <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
                  <L label="Retries"><FormInput value={form.litellm_num_retries} onChange={(e) => set("litellm_num_retries", e.target.value)} /></L>
                  <L label="Timeout"><FormInput value={form.litellm_timeout} onChange={(e) => set("litellm_timeout", e.target.value)} /></L>
                  <L label="Max concurrency"><FormInput value={form.litellm_max_concurrency} onChange={(e) => set("litellm_max_concurrency", e.target.value)} /></L>
                  <L label="Rate limit retries"><FormInput value={form.litellm_rate_limit_max_retries} onChange={(e) => set("litellm_rate_limit_max_retries", e.target.value)} /></L>
                  <L label="Base delay seconds"><FormInput value={form.litellm_rate_limit_base_delay_seconds} onChange={(e) => set("litellm_rate_limit_base_delay_seconds", e.target.value)} /></L>
                  <L label="Max delay seconds"><FormInput value={form.litellm_rate_limit_max_delay_seconds} onChange={(e) => set("litellm_rate_limit_max_delay_seconds", e.target.value)} /></L>
                  <L label="Fallbacks JSON"><FormTextarea value={form.litellm_fallbacks} onChange={(e) => set("litellm_fallbacks", e.target.value)} rows={3} /></L>
                </div>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <ToggleField label="Drop unsupported params" checked={form.litellm_drop_params} onChange={(checked) => set("litellm_drop_params", checked)} />
                  <ToggleField label="Enable caching" checked={form.litellm_caching} onChange={(checked) => set("litellm_caching", checked)} />
                </div>
              </div>

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <L label="Brave API key"><FormInput type="password" value={form.search_brave_api_key} onChange={(e) => set("search_brave_api_key", e.target.value)} placeholder="Leave blank to keep current key" /></L>
                <L label="Firecrawl API key"><FormInput type="password" value={form.search_firecrawl_api_key} onChange={(e) => set("search_firecrawl_api_key", e.target.value)} placeholder="Leave blank to keep current key" /></L>
              </div>
            </section>
          </div>
        ) : null}
      </article>

      <article className={panel}>
        <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-strong)]">Recent logs</h3>
        {logs.length === 0 ? <p className="mt-4 rounded-2xl border border-white/6 bg-[var(--surface-panel-strong)] p-4 text-sm text-[var(--text-muted)]">No logs in current filter window.</p> : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-[var(--text-dim)]"><tr><th className="border-b border-white/6 px-3 py-2">Time</th><th className="border-b border-white/6 px-3 py-2">Level</th><th className="border-b border-white/6 px-3 py-2">Service</th><th className="border-b border-white/6 px-3 py-2">Event</th></tr></thead>
              <tbody>{logs.map((log) => <tr key={`${log.timestamp ?? ""}-${log.event ?? ""}`} className="border-b border-white/6"><td className="px-3 py-3 text-[var(--text-muted)]">{formatLocalDateTime(log.timestamp)}</td><td className="px-3 py-3"><span className={`rounded-full border px-2 py-1 text-[11px] uppercase tracking-wide ${statusTone(log.level)}`}>{String(log.level ?? "info")}</span></td><td className="px-3 py-3 text-[var(--text-strong)]">{log.service ?? "gateway"}</td><td className="px-3 py-3 text-[var(--text-strong)]">{log.event ?? ""}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
