import { z } from "zod";

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
      if (!value?.trim()) {
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
      bot_token: values.telegramToken || "",
      allowed_chat_ids: chatIds ?? [],
      parse_mode: "MarkdownV2",
    },
    llm: {
      provider_id: values.providerId,
      model: values.model,
      api_key: values.apiKey || null,
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
          api_key: values.workerApiKey || null,
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
      dashboard_token: values.dashboardToken || "",
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
      brave_api_key: values.searchProvider === "brave" ? values.braveApiKey || null : null,
      firecrawl_api_key: values.searchProvider === "firecrawl" ? values.firecrawlApiKey || null : null,
    },
  };
}
