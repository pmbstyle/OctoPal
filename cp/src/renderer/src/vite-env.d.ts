/// <reference types="vite/client" />

type DesktopInstallEvent = {
  kind: "step" | "log" | "warning" | "error" | "done";
  message: string;
  detail?: string;
};

type DesktopInstallResult = {
  installDir: string;
  releaseTag: string;
  configPath: string;
  planPath: string;
};

type DesktopInstallState = {
  installed: boolean;
  installDir: string;
  configPath: string;
  planPath: string;
  reason?: string;
};

type DesktopStartResult = {
  ok: true;
  installDir: string;
  detail: string;
};

type DesktopStartFailure = {
  ok: false;
  error: string;
  detail: string;
};

type DesktopStopResult = {
  ok: true;
  installDir: string;
  detail: string;
};

type DesktopStopFailure = {
  ok: false;
  error: string;
  detail: string;
};

type DesktopRuntimeStatus = {
  ok: boolean;
  state: "running" | "stopped" | "error";
  title: string;
  detail: string;
  installDir: string;
  pid?: number | string | null;
  uptime?: string;
  channel?: string;
  octoState?: string;
  launcher?: string;
};

type DesktopPrerequisiteCheck = {
  id: string;
  label: string;
  ok: boolean;
  required: boolean;
  detail: string;
};

type OctopalDesktopApi = {
  loadSettings: () => Promise<{
    language: "en" | "fr" | "es" | "zh";
    theme: "light" | "dark" | "system";
    installDir: string;
  }>;
  saveSettings: (settings: {
    language: "en" | "fr" | "es" | "zh";
    theme: "light" | "dark" | "system";
    installDir: string;
  }) => Promise<{
    language: "en" | "fr" | "es" | "zh";
    theme: "light" | "dark" | "system";
    installDir: string;
  }>;
  chooseInstallDir: () => Promise<string | null>;
  closeWindow: () => Promise<void>;
  minimizeWindow: () => Promise<void>;
  toggleMaximizeWindow: () => Promise<void>;
  checkPrerequisites: () => Promise<DesktopPrerequisiteCheck[]>;
  getInstallState: () => Promise<DesktopInstallState>;
  loadOctopalConfig: () => Promise<unknown>;
  saveOctopalConfig: (config: unknown) => Promise<DesktopInstallState>;
  writeInstallPlan: (payload: unknown) => Promise<{ planPath: string }>;
  installOctopal: (payload: unknown) => Promise<DesktopInstallResult>;
  startOctopal: (installDir: string) => Promise<DesktopStartResult | DesktopStartFailure>;
  stopOctopal: (installDir: string) => Promise<DesktopStopResult | DesktopStopFailure>;
  getOctopalStatus: (installDir: string) => Promise<DesktopRuntimeStatus>;
  onInstallEvent: (callback: (event: DesktopInstallEvent) => void) => () => void;
};

interface Window {
  octopalDesktop?: OctopalDesktopApi;
}
