import type { InstallForm } from "./install";
import { messages } from "./i18n";
import type { StepId } from "./appTypes";

export const stepLabels: Record<StepId, keyof typeof messages.en> = {
  location: "stepLocation",
  channel: "stepChannel",
  "octo-llm": "stepLlm",
  "worker-llm": "stepWorkerLlm",
  search: "stepTools",
  dashboard: "stepDashboard",
  review: "stepReview",
};

export const stepSpeech: Record<StepId, keyof typeof messages.en> = {
  location: "speechInstall",
  channel: "speechChannel",
  "octo-llm": "speechLlm",
  "worker-llm": "speechWorkerLlm",
  search: "speechSearch",
  dashboard: "speechDashboard",
  review: "speechReview",
};

export function getWizardSteps(useSameWorkerModel: boolean): StepId[] {
  return useSameWorkerModel
    ? ["location", "channel", "octo-llm", "search", "dashboard", "review"]
    : ["location", "channel", "octo-llm", "worker-llm", "search", "dashboard", "review"];
}

export function getValidationFields(step: StepId, values: InstallForm): Array<keyof InstallForm> {
  if (step === "location") {
    return ["installDir"];
  }

  if (step === "channel") {
    return values.channel === "telegram" ? ["channel", "telegramToken"] : ["channel", "whatsappAllowedNumbers"];
  }

  if (step === "octo-llm") {
    return values.providerId === "custom" ? ["providerId", "model", "apiBase"] : ["providerId", "model", "apiKey"];
  }

  if (step === "worker-llm") {
    return values.workerProviderId === "custom"
      ? ["workerProviderId", "workerModel", "workerApiBase"]
      : ["workerProviderId", "workerModel", "workerApiKey"];
  }

  if (step === "search") {
    if (values.searchProvider === "brave") {
      return ["searchProvider", "braveApiKey"];
    }
    if (values.searchProvider === "firecrawl") {
      return ["searchProvider", "firecrawlApiKey"];
    }
  }

  if (step === "dashboard") {
    return ["dashboardPort"];
  }

  return [];
}
