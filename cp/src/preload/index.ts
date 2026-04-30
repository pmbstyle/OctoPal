import { contextBridge, ipcRenderer } from "electron";

type DesktopSettings = {
  language: "en" | "fr" | "es" | "zh";
  theme: "light" | "dark" | "system";
  installDir: string;
};

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

contextBridge.exposeInMainWorld("octopalDesktop", {
  loadSettings: () => ipcRenderer.invoke("desktop:load-settings") as Promise<DesktopSettings>,
  saveSettings: (settings: DesktopSettings) =>
    ipcRenderer.invoke("desktop:save-settings", settings) as Promise<DesktopSettings>,
  chooseInstallDir: () => ipcRenderer.invoke("desktop:choose-install-dir") as Promise<string | null>,
  closeWindow: () => ipcRenderer.invoke("desktop:window-control", "close") as Promise<void>,
  minimizeWindow: () => ipcRenderer.invoke("desktop:window-control", "minimize") as Promise<void>,
  toggleMaximizeWindow: () => ipcRenderer.invoke("desktop:window-control", "maximize") as Promise<void>,
  checkPrerequisites: () =>
    ipcRenderer.invoke("desktop:check-prerequisites") as Promise<
      Array<{ id: string; label: string; ok: boolean; detail: string }>
    >,
  getInstallState: () => ipcRenderer.invoke("desktop:get-install-state") as Promise<DesktopInstallState>,
  loadOctopalConfig: () => ipcRenderer.invoke("desktop:load-octopal-config") as Promise<unknown>,
  saveOctopalConfig: (config: unknown) =>
    ipcRenderer.invoke("desktop:save-octopal-config", config) as Promise<DesktopInstallState>,
  writeInstallPlan: (payload: unknown) =>
    ipcRenderer.invoke("desktop:write-install-plan", payload) as Promise<{ planPath: string }>,
  installOctopal: (payload: unknown) =>
    ipcRenderer.invoke("desktop:install-octopal", payload) as Promise<DesktopInstallResult>,
  startOctopal: (installDir: string) =>
    ipcRenderer.invoke("desktop:start-octopal", installDir) as Promise<DesktopStartResult | DesktopStartFailure>,
  stopOctopal: (installDir: string) =>
    ipcRenderer.invoke("desktop:stop-octopal", installDir) as Promise<DesktopStopResult | DesktopStopFailure>,
  onInstallEvent: (callback: (event: DesktopInstallEvent) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, installEvent: DesktopInstallEvent) => callback(installEvent);
    ipcRenderer.on("desktop:install-event", handler);
    return () => ipcRenderer.removeListener("desktop:install-event", handler);
  },
});
