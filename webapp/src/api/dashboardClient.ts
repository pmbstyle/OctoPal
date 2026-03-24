import type { paths } from "./types";

type OverviewResponse =
  paths["/api/dashboard/v2/overview"]["get"]["responses"]["200"]["content"]["application/json"];
type IncidentsResponse =
  paths["/api/dashboard/v2/incidents"]["get"]["responses"]["200"]["content"]["application/json"];
type OctoResponse =
  paths["/api/dashboard/v2/octo"]["get"]["responses"]["200"]["content"]["application/json"];
type WorkersResponse =
  paths["/api/dashboard/v2/workers"]["get"]["responses"]["200"]["content"]["application/json"];
type SystemResponse =
  paths["/api/dashboard/v2/system"]["get"]["responses"]["200"]["content"]["application/json"];
type ActionsResponse =
  paths["/api/dashboard/v2/actions"]["get"]["responses"]["200"]["content"]["application/json"];

export type WorkerTemplate = {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  available_tools: string[];
  required_permissions: string[];
  model?: string | null;
  max_thinking_steps: number;
  default_timeout_seconds: number;
  can_spawn_children: boolean;
  allowed_child_templates: string[];
  created_at?: string;
  updated_at?: string;
};

type ActionRequest = {
  action: "restart_worker" | "retry_failed" | "clear_control_queue";
  worker_id?: string;
  confirm?: boolean;
  reason?: string;
};

export type DashboardQueryParams = {
  windowMinutes: 15 | 60 | 240 | 1440;
  service: "all" | "gateway" | "octo" | "telegram" | "exec_run" | "mcp" | "workers";
  environment: "all" | "local" | "dev" | "staging" | "prod";
  token?: string;
};

const defaultHeaders: HeadersInit = { "content-type": "application/json" };

function withQuery(path: string, params: DashboardQueryParams): string {
  const query = new URLSearchParams();
  query.set("window_minutes", String(params.windowMinutes));
  query.set("service", params.service);
  query.set("environment", params.environment);
  return `${path}?${query.toString()}`;
}

async function fetchJson<T>(url: string, token?: string): Promise<T> {
  const headers: HeadersInit = token
    ? { ...defaultHeaders, "x-octopal-token": token }
    : defaultHeaders;
  const response = await fetch(url, { method: "GET", headers });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function mutateJson<T>(url: string, method: "POST" | "PUT" | "DELETE", token?: string, body?: unknown): Promise<T> {
  const headers: HeadersInit = token
    ? { ...defaultHeaders, "x-octopal-token": token }
    : defaultHeaders;
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchOverview(params: DashboardQueryParams): Promise<OverviewResponse> {
  return fetchJson<OverviewResponse>(withQuery("/api/dashboard/v2/overview", params), params.token);
}

export async function fetchIncidents(params: DashboardQueryParams): Promise<IncidentsResponse> {
  return fetchJson<IncidentsResponse>(withQuery("/api/dashboard/v2/incidents", params), params.token);
}

export async function fetchOcto(params: DashboardQueryParams): Promise<OctoResponse> {
  return fetchJson<OctoResponse>(withQuery("/api/dashboard/v2/octo", params), params.token);
}

export async function fetchWorkers(params: DashboardQueryParams): Promise<WorkersResponse> {
  return fetchJson<WorkersResponse>(withQuery("/api/dashboard/v2/workers", params), params.token);
}

export async function fetchSystem(params: DashboardQueryParams): Promise<SystemResponse> {
  return fetchJson<SystemResponse>(withQuery("/api/dashboard/v2/system", params), params.token);
}

export async function fetchActions(params: DashboardQueryParams): Promise<ActionsResponse> {
  return fetchJson<ActionsResponse>(withQuery("/api/dashboard/v2/actions", params), params.token);
}

export async function runDashboardAction(payload: ActionRequest, token?: string): Promise<Record<string, unknown>> {
  return mutateJson<Record<string, unknown>>("/api/dashboard/actions", "POST", token, payload);
}

export async function fetchWorkerTemplates(token?: string): Promise<WorkerTemplate[]> {
  const payload = await fetchJson<{ count: number; templates: WorkerTemplate[] }>("/api/dashboard/worker-templates", token);
  return payload.templates ?? [];
}

export async function createWorkerTemplate(payload: WorkerTemplate, token?: string): Promise<WorkerTemplate> {
  const response = await mutateJson<{ status: string; template: WorkerTemplate }>(
    "/api/dashboard/worker-templates",
    "POST",
    token,
    payload,
  );
  return response.template;
}

export async function updateWorkerTemplate(payload: WorkerTemplate, token?: string): Promise<WorkerTemplate> {
  const response = await mutateJson<{ status: string; template: WorkerTemplate }>(
    `/api/dashboard/worker-templates/${encodeURIComponent(payload.id)}`,
    "PUT",
    token,
    payload,
  );
  return response.template;
}

export async function deleteWorkerTemplate(templateId: string, token?: string): Promise<void> {
  await mutateJson<{ status: string }>(
    `/api/dashboard/worker-templates/${encodeURIComponent(templateId)}`,
    "DELETE",
    token,
  );
}
