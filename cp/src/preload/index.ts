import { contextBridge, ipcRenderer } from "electron";

type DesktopSettings = {
  language: "en" | "fr" | "es" | "zh";
  theme: "light" | "dark" | "system";
  installDir: string;
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
  writeInstallPlan: (payload: unknown) =>
    ipcRenderer.invoke("desktop:write-install-plan", payload) as Promise<{ planPath: string }>,
});
