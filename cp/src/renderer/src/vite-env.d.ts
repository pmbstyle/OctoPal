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

type DesktopStartResult = {
  installDir: string;
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
  checkPrerequisites: () => Promise<Array<{ id: string; label: string; ok: boolean; detail: string }>>;
  writeInstallPlan: (payload: unknown) => Promise<{ planPath: string }>;
  installOctopal: (payload: unknown) => Promise<DesktopInstallResult>;
  startOctopal: (installDir: string) => Promise<DesktopStartResult>;
  onInstallEvent: (callback: (event: DesktopInstallEvent) => void) => () => void;
};

interface Window {
  octopalDesktop?: OctopalDesktopApi;
}
