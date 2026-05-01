import { z } from "zod";

export const EXISTING_SECRET_VALUE = "__OCTOPAL_DESKTOP_EXISTING_SECRET__";

export function isExistingSecret(value: string | undefined | null): boolean {
  return value === EXISTING_SECRET_VALUE;
}

export const providers = [
  { id: "openrouter", label: "OpenRouter", model: "anthropic/claude-sonnet-4" },
  { id: "zai", label: "Z.AI", model: "glm-4.6" },
  { id: "openai", label: "OpenAI", model: "gpt-5.2" },
  { id: "anthropic", label: "Anthropic", model: "claude-sonnet-4-5" },
  { id: "google", label: "Google Gemini", model: "gemini-2.5-pro" },
  { id: "mistral", label: "Mistral", model: "mistral-large-latest" },
  { id: "together", label: "Together AI", model: "meta-llama/Llama-3.3-70B-Instruct-Turbo" },
  { id: "groq", label: "Groq", model: "llama-3.3-70b-versatile" },
  { id: "custom", label: "Custom LiteLLM", model: "" },
] as const;

export const searchProviders = [
  { id: "brave", label: "Brave Search", keyField: "braveApiKey" },
  { id: "firecrawl", label: "Firecrawl", keyField: "firecrawlApiKey" },
] as const;

export const installSchema = z
  .object({
    installDir: z.string().trim().min(1),
    channel: z.enum(["telegram", "whatsapp"]),
    telegramToken: z.string().optional(),
    allowedChatIds: z.string().optional(),
    whatsappMode: z.enum(["personal", "separate"]),
    whatsappAllowedNumbers: z.string().optional(),
    providerId: z.string().trim().min(1),
    model: z.string().trim().min(1),
    apiKey: z.string().optional(),
    apiBase: z.string().optional(),
    sameWorker: z.boolean(),
    workerProviderId: z.string().optional(),
    workerModel: z.string().optional(),
    workerApiKey: z.string().optional(),
    workerApiBase: z.string().optional(),
    searchProvider: z.enum(["brave", "firecrawl"]).optional(),
    braveApiKey: z.string().optional(),
    firecrawlApiKey: z.string().optional(),
    dashboardEnabled: z.boolean(),
    dashboardPort: z.number().int().min(1).max(65535),
    dashboardToken: z.string().optional(),
  })
  .superRefine((values, context) => {
    const requireField = (path: string, value: string | undefined) => {
      if (!value?.trim() && !isExistingSecret(value)) {
        context.addIssue({ code: "custom", path: [path], message: "Required" });
      }
    };

    if (values.channel === "telegram") {
      requireField("telegramToken", values.telegramToken);
    }

    if (values.channel === "whatsapp") {
      requireField("whatsappAllowedNumbers", values.whatsappAllowedNumbers);
    }

    if (values.providerId === "custom") {
      requireField("apiBase", values.apiBase);
    } else {
      requireField("apiKey", values.apiKey);
    }

    if (!values.sameWorker) {
      requireField("workerProviderId", values.workerProviderId);
      requireField("workerModel", values.workerModel);
      if (values.workerProviderId === "custom") {
        requireField("workerApiBase", values.workerApiBase);
      } else {
        requireField("workerApiKey", values.workerApiKey);
      }
    }

    if (values.searchProvider === "brave") {
      requireField("braveApiKey", values.braveApiKey);
    }

    if (values.searchProvider === "firecrawl") {
      requireField("firecrawlApiKey", values.firecrawlApiKey);
    }
  });

export type InstallForm = z.infer<typeof installSchema>;

function secretString(value: string | undefined): string {
  return isExistingSecret(value) ? "" : value || "";
}

function secretNullable(value: string | undefined): string | null {
  return isExistingSecret(value) ? null : value || null;
}

export const defaultInstallValues: InstallForm = {
  installDir: "",
  channel: "telegram",
  telegramToken: "",
  allowedChatIds: "",
  whatsappMode: "separate",
  whatsappAllowedNumbers: "",
  providerId: "openrouter",
  model: "anthropic/claude-sonnet-4",
  apiKey: "",
  apiBase: "",
  sameWorker: false,
  workerProviderId: "openrouter",
  workerModel: "anthropic/claude-sonnet-4",
  workerApiKey: "",
  workerApiBase: "",
  searchProvider: undefined,
  braveApiKey: "",
  firecrawlApiKey: "",
  dashboardEnabled: true,
  dashboardPort: 8000,
  dashboardToken: "",
};

export function buildOctopalConfig(values: InstallForm) {
  const chatIds = values.allowedChatIds
    ?.split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const whatsappNumbers = values.whatsappAllowedNumbers
    ?.split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  const workerProviderId = values.workerProviderId || values.providerId;
  const workerModel = values.workerModel || values.model;

  return {
    user_channel: values.channel,
    telegram: {
      bot_token: secretString(values.telegramToken),
      allowed_chat_ids: chatIds ?? [],
      parse_mode: "MarkdownV2",
    },
    llm: {
      provider_id: values.providerId,
      model: values.model,
      api_key: secretNullable(values.apiKey),
      api_base: values.apiBase || null,
      model_prefix: null,
    },
    worker_llm_default: values.sameWorker
      ? {
          provider_id: null,
          model: null,
          api_key: null,
          api_base: null,
          model_prefix: null,
        }
      : {
          provider_id: workerProviderId,
          model: workerModel,
          api_key: secretNullable(values.workerApiKey),
          api_base: values.workerApiBase || null,
          model_prefix: null,
        },
    worker_llm_overrides: {},
    storage: {
      state_dir: "data",
      workspace_dir: "workspace",
    },
    gateway: {
      host: "0.0.0.0",
      port: values.dashboardPort,
      dashboard_token: secretString(values.dashboardToken),
      tailscale_auto_serve: true,
      tailscale_ips: "",
      webapp_enabled: values.dashboardEnabled,
      webapp_dist_dir: null,
    },
    whatsapp: {
      mode: values.whatsappMode,
      allowed_numbers: whatsappNumbers ?? [],
      auth_dir: null,
      bridge_host: "127.0.0.1",
      bridge_port: 8765,
      callback_token: "",
      node_command: "node",
    },
    search: {
      brave_api_key: values.searchProvider === "brave" ? secretNullable(values.braveApiKey) : null,
      firecrawl_api_key: values.searchProvider === "firecrawl" ? secretNullable(values.firecrawlApiKey) : null,
    },
  };
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function listValue(value: unknown): string {
  return Array.isArray(value) ? value.map((item) => String(item)).join(", ") : "";
}

export function formValuesFromOctopalConfig(config: unknown, installDir: string): InstallForm {
  const root = recordValue(config);
  const telegram = recordValue(root.telegram);
  const whatsapp = recordValue(root.whatsapp);
  const llm = recordValue(root.llm);
  const workerLlm = recordValue(root.worker_llm_default);
  const gateway = recordValue(root.gateway);
  const search = recordValue(root.search);
  const braveApiKey = stringValue(search.brave_api_key);
  const firecrawlApiKey = stringValue(search.firecrawl_api_key);
  const workerProviderId = stringValue(workerLlm.provider_id);

  return {
    ...defaultInstallValues,
    installDir,
    channel: root.user_channel === "whatsapp" ? "whatsapp" : "telegram",
    telegramToken: stringValue(telegram.bot_token),
    allowedChatIds: listValue(telegram.allowed_chat_ids),
    whatsappMode: whatsapp.mode === "personal" ? "personal" : "separate",
    whatsappAllowedNumbers: listValue(whatsapp.allowed_numbers),
    providerId: stringValue(llm.provider_id, defaultInstallValues.providerId),
    model: stringValue(llm.model, defaultInstallValues.model),
    apiKey: stringValue(llm.api_key),
    apiBase: stringValue(llm.api_base),
    sameWorker: !workerProviderId,
    workerProviderId: workerProviderId || defaultInstallValues.workerProviderId,
    workerModel: stringValue(workerLlm.model, defaultInstallValues.workerModel),
    workerApiKey: stringValue(workerLlm.api_key),
    workerApiBase: stringValue(workerLlm.api_base),
    searchProvider: braveApiKey ? "brave" : firecrawlApiKey ? "firecrawl" : undefined,
    braveApiKey,
    firecrawlApiKey,
    dashboardEnabled: gateway.webapp_enabled !== false,
    dashboardPort: numberValue(gateway.port, defaultInstallValues.dashboardPort),
    dashboardToken: stringValue(gateway.dashboard_token),
  };
}
