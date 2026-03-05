import type { paths } from "./types";

type OverviewResponse =
  paths["/api/dashboard/v2/overview"]["get"]["responses"]["200"]["content"]["application/json"];
type IncidentsResponse =
  paths["/api/dashboard/v2/incidents"]["get"]["responses"]["200"]["content"]["application/json"];
type QueenResponse =
  paths["/api/dashboard/v2/queen"]["get"]["responses"]["200"]["content"]["application/json"];
type WorkersResponse =
  paths["/api/dashboard/v2/workers"]["get"]["responses"]["200"]["content"]["application/json"];
type SystemResponse =
  paths["/api/dashboard/v2/system"]["get"]["responses"]["200"]["content"]["application/json"];
type ActionsResponse =
  paths["/api/dashboard/v2/actions"]["get"]["responses"]["200"]["content"]["application/json"];

type ActionRequest = {
  action: "restart_worker" | "retry_failed" | "clear_control_queue";
  worker_id?: string;
  confirm?: boolean;
  reason?: string;
};

export type DashboardQueryParams = {
  windowMinutes: 15 | 60 | 240 | 1440;
  service: "all" | "gateway" | "queen" | "telegram" | "exec_run" | "mcp" | "workers";
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
    ? { ...defaultHeaders, "x-broodmind-token": token }
    : defaultHeaders;
  const response = await fetch(url, { method: "GET", headers });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchOverview(params: DashboardQueryParams): Promise<OverviewResponse> {
  return fetchJson<OverviewResponse>(withQuery("/api/dashboard/v2/overview", params), params.token);
}

export async function fetchIncidents(params: DashboardQueryParams): Promise<IncidentsResponse> {
  return fetchJson<IncidentsResponse>(withQuery("/api/dashboard/v2/incidents", params), params.token);
}

export async function fetchQueen(params: DashboardQueryParams): Promise<QueenResponse> {
  return fetchJson<QueenResponse>(withQuery("/api/dashboard/v2/queen", params), params.token);
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
  const headers: HeadersInit = token
    ? { ...defaultHeaders, "x-broodmind-token": token }
    : defaultHeaders;

  const response = await fetch("/api/dashboard/actions", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Action failed: ${response.status}`);
  }
  return (await response.json()) as Record<string, unknown>;
}
