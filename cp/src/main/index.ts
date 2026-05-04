import { app, BrowserWindow, dialog, ipcMain, nativeTheme, type OpenDialogOptions } from "electron";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";

import {
  checkDesktopAppUpdate,
  downloadDesktopAppUpdate,
  getDesktopAppUpdateStatus,
  installDesktopAppUpdate,
  scheduleDesktopAppUpdateCheck,
} from "./appUpdater";
import {
  authorizeConnector,
  disconnectConnector,
  getConnectorStatus,
  type ConnectorAuthPayload,
  type ConnectorName,
} from "./connectors";
import {
  checkOctopalUpdateSafely,
  getOctopalStatusSafely,
  runInstall,
  startOctopalSafely,
  stopOctopalSafely,
  updateOctopalSafely,
  type InstallEvent,
  type InstallPayload,
} from "./installer";
import { getWhatsAppLinkStatus, startWhatsAppLink, stopWhatsAppLink } from "./whatsapp";

const execFileAsync = promisify(execFile);
const EXISTING_SECRET_VALUE = "__OCTOPAL_DESKTOP_EXISTING_SECRET__";

type DesktopSettings = {
  language: "en" | "fr" | "es" | "zh";
  theme: "light" | "dark" | "system";
  installDir: string;
};

type InstallState = {
  installed: boolean;
  installDir: string;
  configPath: string;
  planPath: string;
  reason?: string;
};

type PrerequisiteCheck = {
  id: string;
  label: string;
  ok: boolean;
  required: boolean;
  detail: string;
};

const defaultSettings: DesktopSettings = {
  language: "en",
  theme: "system",
  installDir: "",
};

function settingsPath(): string {
  return join(app.getPath("userData"), "octopal-desktop.json");
}

async function readSettings(): Promise<DesktopSettings> {
  try {
    const raw = await readFile(settingsPath(), "utf8");
    return { ...defaultSettings, ...JSON.parse(raw) };
  } catch {
    return defaultSettings;
  }
}

async function writeSettings(settings: DesktopSettings): Promise<DesktopSettings> {
  const next = { ...defaultSettings, ...settings };
  await mkdir(app.getPath("userData"), { recursive: true });
  await writeFile(settingsPath(), JSON.stringify(next, null, 2), "utf8");
  nativeTheme.themeSource = next.theme;
  return next;
}

async function pathExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function cloneJsonRecord(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    return {};
  }
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

function deepMergeRecords(existing: Record<string, unknown>, incoming: Record<string, unknown>): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...existing };
  for (const [key, value] of Object.entries(incoming)) {
    const current = merged[key];
    if (isRecord(current) && isRecord(value)) {
      merged[key] = deepMergeRecords(current, value);
      continue;
    }
    merged[key] = value;
  }
  return merged;
}

function getNested(root: Record<string, unknown>, path: string[]): unknown {
  let current: unknown = root;
  for (const segment of path) {
    if (!isRecord(current)) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
}

function setNested(root: Record<string, unknown>, path: string[], value: unknown): void {
  let current = root;
  for (const segment of path.slice(0, -1)) {
    const next = current[segment];
    if (!isRecord(next)) {
      current[segment] = {};
    }
    current = current[segment] as Record<string, unknown>;
  }
  current[path[path.length - 1]] = value;
}

function isBlankSecret(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

function preserveSecretIfBlank(
  merged: Record<string, unknown>,
  existing: Record<string, unknown>,
  path: string[],
  options: { sameProviderPath?: string[] } = {},
): void {
  const incomingValue = getNested(merged, path);
  const existingValue = getNested(existing, path);
  if (isBlankSecret(incomingValue) && !isBlankSecret(existingValue)) {
    if (options.sameProviderPath) {
      const mergedProvider = getNested(merged, options.sameProviderPath);
      const existingProvider = getNested(existing, options.sameProviderPath);
      if (mergedProvider !== existingProvider) {
        return;
      }
    }
    setNested(merged, path, existingValue);
  }
}

function mergeConfigForDesktopSave(existingConfig: unknown, incomingConfig: unknown): Record<string, unknown> {
  const existing = cloneJsonRecord(existingConfig);
  const incoming = cloneJsonRecord(incomingConfig);
  const merged = deepMergeRecords(existing, incoming);

  preserveSecretIfBlank(merged, existing, ["telegram", "bot_token"]);
  preserveSecretIfBlank(merged, existing, ["llm", "api_key"], { sameProviderPath: ["llm", "provider_id"] });
  preserveSecretIfBlank(merged, existing, ["worker_llm_default", "api_key"], {
    sameProviderPath: ["worker_llm_default", "provider_id"],
  });
  preserveSecretIfBlank(merged, existing, ["gateway", "dashboard_token"]);
  preserveSecretIfBlank(merged, existing, ["whatsapp", "callback_token"]);
  preserveSecretIfBlank(merged, existing, ["search", "brave_api_key"]);
  preserveSecretIfBlank(merged, existing, ["search", "firecrawl_api_key"]);
  preserveSecretIfBlank(merged, existing, ["connectors", "instances", "google", "credentials", "client_secret"], {
    sameProviderPath: ["connectors", "instances", "google", "credentials", "client_id"],
  });
  preserveSecretIfBlank(merged, existing, ["connectors", "instances", "google", "auth", "refresh_token"]);
  preserveSecretIfBlank(merged, existing, ["connectors", "instances", "google", "auth", "access_token"]);
  preserveSecretIfBlank(merged, existing, ["connectors", "instances", "github", "auth", "access_token"]);

  return merged;
}

function sanitizeConfigForRenderer(config: unknown): Record<string, unknown> {
  const sanitized = cloneJsonRecord(config);
  const original = cloneJsonRecord(config);
  const maskedValue = (path: string[]) => {
    const value = getNested(original, path);
    return typeof value === "string" && value.trim() ? EXISTING_SECRET_VALUE : "";
  };
  const maskedNullableValue = (path: string[]) => {
    const value = getNested(original, path);
    return typeof value === "string" && value.trim() ? EXISTING_SECRET_VALUE : null;
  };
  setNested(sanitized, ["telegram", "bot_token"], maskedValue(["telegram", "bot_token"]));
  setNested(sanitized, ["llm", "api_key"], maskedNullableValue(["llm", "api_key"]));
  setNested(sanitized, ["worker_llm_default", "api_key"], maskedNullableValue(["worker_llm_default", "api_key"]));
  setNested(sanitized, ["gateway", "dashboard_token"], maskedValue(["gateway", "dashboard_token"]));
  setNested(sanitized, ["whatsapp", "callback_token"], maskedValue(["whatsapp", "callback_token"]));
  setNested(sanitized, ["search", "brave_api_key"], maskedNullableValue(["search", "brave_api_key"]));
  setNested(sanitized, ["search", "firecrawl_api_key"], maskedNullableValue(["search", "firecrawl_api_key"]));
  setNested(sanitized, ["observability", "langfuse_secret_key"], maskedNullableValue(["observability", "langfuse_secret_key"]));
  setNested(
    sanitized,
    ["connectors", "instances", "google", "credentials", "client_secret"],
    maskedNullableValue(["connectors", "instances", "google", "credentials", "client_secret"]),
  );
  setNested(
    sanitized,
    ["connectors", "instances", "google", "auth", "refresh_token"],
    maskedNullableValue(["connectors", "instances", "google", "auth", "refresh_token"]),
  );
  setNested(
    sanitized,
    ["connectors", "instances", "google", "auth", "access_token"],
    maskedNullableValue(["connectors", "instances", "google", "auth", "access_token"]),
  );
  setNested(
    sanitized,
    ["connectors", "instances", "github", "auth", "access_token"],
    maskedNullableValue(["connectors", "instances", "github", "auth", "access_token"]),
  );
  return sanitized;
}

async function scrubInstallPlan(planPath: string): Promise<void> {
  try {
    const raw = await readFile(planPath, "utf8");
    const plan = JSON.parse(raw) as Record<string, unknown>;
    if (!plan || typeof plan !== "object" || !("octopalConfig" in plan)) {
      return;
    }

    delete plan.octopalConfig;
    await writeFile(planPath, JSON.stringify(plan, null, 2), "utf8");
  } catch {
    // Legacy install plans are optional metadata; failures should not block app startup.
  }
}

async function getInstallState(): Promise<InstallState> {
  const settings = await readSettings();
  const installDir = settings.installDir;
  const configPath = installDir ? join(installDir, "config.json") : "";
  const planPath = installDir ? join(installDir, ".octopal-desktop", "install-plan.json") : "";

  if (!installDir) {
    return { installed: false, installDir, configPath, planPath, reason: "Install directory is not selected." };
  }

  const hasProject = await pathExists(join(installDir, "pyproject.toml"));
  const hasConfig = await pathExists(configPath);
  if (hasProject && hasConfig) {
    await scrubInstallPlan(planPath);
  }

  return {
    installed: hasProject && hasConfig,
    installDir,
    configPath,
    planPath,
    reason: hasProject && hasConfig ? undefined : "Octopal project or config.json was not found.",
  };
}

async function loadInstalledConfig(): Promise<unknown> {
  const state = await getInstallState();
  if (!state.installed) {
    throw new Error(state.reason ?? "Octopal is not installed.");
  }

  return sanitizeConfigForRenderer(JSON.parse(await readFile(state.configPath, "utf8")));
}

async function saveInstalledConfig(config: unknown): Promise<InstallState> {
  const state = await getInstallState();
  if (!state.installed) {
    throw new Error(state.reason ?? "Octopal is not installed.");
  }

  const existing = JSON.parse(await readFile(state.configPath, "utf8"));
  const merged = mergeConfigForDesktopSave(existing, config);
  await writeFile(state.configPath, JSON.stringify(merged, null, 2), "utf8");
  return getInstallState();
}

function resolveBrandIcon(): string | undefined {
  const primaryIcon = process.platform === "darwin" ? "octo.png" : "octo.ico";
  const filenames = [primaryIcon, primaryIcon === "octo.ico" ? "octo.png" : "octo.ico"];
  const roots = [process.cwd(), app.getAppPath(), process.resourcesPath];

  for (const root of roots) {
    for (const filename of filenames) {
      const candidate = join(root, "assets", filename);
      if (existsSync(candidate)) {
        return candidate;
      }
    }
  }

  return undefined;
}

function createWindow(): void {
  const icon = resolveBrandIcon();
  const mainWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 920,
    minHeight: 680,
    title: "Octopal Desktop",
    ...(icon ? { icon } : {}),
    backgroundColor: "#00000000",
    frame: false,
    transparent: true,
    hasShadow: true,
    webPreferences: {
      preload: join(__dirname, "../preload/index.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (process.env.ELECTRON_RENDERER_URL) {
    void mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

async function checkCommand(command: string, args: string[]): Promise<{ ok: boolean; detail: string }> {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, { timeout: 5000, windowsHide: true });
    return { ok: true, detail: (stdout || stderr).trim().split(/\r?\n/)[0] || "Available" };
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
      return { ok: false, detail: `${command} was not found in PATH. Install it or restart Octopal Desktop after updating PATH.` };
    }
    const message = error instanceof Error ? error.message : "Unavailable";
    return { ok: false, detail: message };
  }
}

function parseNodeMajor(version: string): number | null {
  const match = version.trim().match(/^v?(?<major>\d+)/);
  if (!match?.groups?.major) {
    return null;
  }
  return Number.parseInt(match.groups.major, 10);
}

async function checkNode20(): Promise<{ ok: boolean; detail: string }> {
  const node = await checkCommand("node", ["--version"]);
  if (!node.ok) {
    return node;
  }

  const major = parseNodeMajor(node.detail);
  if (major === null) {
    return { ok: false, detail: `Could not read Node.js version: ${node.detail}` };
  }

  if (major < 20) {
    return { ok: false, detail: `Node.js 20+ is required for WhatsApp bridge. Found ${node.detail}.` };
  }

  return node;
}

async function checkDockerRuntime(): Promise<{ ok: boolean; detail: string }> {
  const docker = await checkCommand("docker", ["--version"]);
  if (!docker.ok) {
    return docker;
  }

  const daemon = await checkCommand("docker", ["info", "--format", "{{.ServerVersion}}"]);
  if (!daemon.ok) {
    return { ok: false, detail: `Docker CLI is installed, but the daemon is unavailable: ${daemon.detail}` };
  }

  return { ok: true, detail: `Docker ${daemon.detail}` };
}

ipcMain.handle("desktop:load-settings", async () => readSettings());
ipcMain.handle("desktop:save-settings", async (_event, settings: DesktopSettings) => writeSettings(settings));
ipcMain.handle("desktop:get-install-state", async () => getInstallState());
ipcMain.handle("desktop:load-octopal-config", async () => loadInstalledConfig());
ipcMain.handle("desktop:save-octopal-config", async (_event, config: unknown) => saveInstalledConfig(config));

ipcMain.handle("desktop:choose-install-dir", async (event) => {
  const parentWindow = BrowserWindow.fromWebContents(event.sender) ?? undefined;
  const options: OpenDialogOptions = {
    title: "Choose Octopal install folder",
    properties: ["openDirectory", "createDirectory"],
  };
  const result = parentWindow ? await dialog.showOpenDialog(parentWindow, options) : await dialog.showOpenDialog(options);

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  return result.filePaths[0];
});

ipcMain.handle("desktop:window-control", (event, action: "close" | "minimize" | "maximize") => {
  const window = BrowserWindow.fromWebContents(event.sender);
  if (!window) {
    return;
  }

  if (action === "close") {
    window.close();
    return;
  }

  if (action === "minimize") {
    window.minimize();
    return;
  }

  if (window.isMaximized()) {
    window.unmaximize();
  } else {
    window.maximize();
  }
});

ipcMain.handle("desktop:check-prerequisites", async (): Promise<PrerequisiteCheck[]> => {
  const checks = await Promise.all([
    checkCommand("git", ["--version"]),
    checkCommand("uv", ["--version"]),
    checkDockerRuntime(),
    checkNode20(),
  ]);

  return [
    { id: "git", label: "Git", required: true, ...checks[0] },
    { id: "uv", label: "uv", required: false, ...checks[1] },
    { id: "docker", label: "Docker runtime", required: false, ...checks[2] },
    { id: "node", label: "Node.js 20+", required: false, ...checks[3] },
  ];
});

ipcMain.handle("desktop:write-install-plan", async (_event, payload: unknown) => {
  const settings = await readSettings();
  if (!settings.installDir) {
    throw new Error("Install directory is not selected.");
  }

  const planDir = join(settings.installDir, ".octopal-desktop");
  await mkdir(planDir, { recursive: true });
  const planPath = join(planDir, "install-plan.json");
  const payloadRecord = payload && typeof payload === "object" && !Array.isArray(payload) ? { ...payload } : {};
  delete (payloadRecord as Record<string, unknown>).octopalConfig;
  await writeFile(planPath, JSON.stringify(payloadRecord, null, 2), "utf8");
  return { planPath };
});

ipcMain.handle("desktop:install-octopal", async (event, payload: InstallPayload) => {
  const sender = event.sender;
  const emit = (installEvent: InstallEvent) => {
    if (!sender.isDestroyed()) {
      sender.send("desktop:install-event", installEvent);
    }
  };

  try {
    return await runInstall(payload, emit);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Installation failed.";
    emit({ kind: "error", message });
    throw error;
  }
});

ipcMain.handle("desktop:start-octopal", async (_event, installDir: string) => startOctopalSafely(installDir));
ipcMain.handle("desktop:stop-octopal", async (_event, installDir: string) => stopOctopalSafely(installDir));
ipcMain.handle("desktop:get-octopal-status", async (_event, installDir: string) => getOctopalStatusSafely(installDir));
ipcMain.handle("desktop:check-octopal-update", async (_event, installDir: string) => checkOctopalUpdateSafely(installDir));
ipcMain.handle("desktop:update-octopal", async (_event, installDir: string) => updateOctopalSafely(installDir));
ipcMain.handle("desktop:get-app-update-status", () => getDesktopAppUpdateStatus());
ipcMain.handle("desktop:check-app-update", () => checkDesktopAppUpdate());
ipcMain.handle("desktop:download-app-update", () => downloadDesktopAppUpdate());
ipcMain.handle("desktop:install-app-update", () => installDesktopAppUpdate());
ipcMain.handle("desktop:get-connector-status", async (_event, installDir: string) => getConnectorStatus(installDir));
ipcMain.handle("desktop:authorize-connector", async (_event, installDir: string, payload: ConnectorAuthPayload) =>
  authorizeConnector(installDir, payload),
);
ipcMain.handle(
  "desktop:disconnect-connector",
  async (_event, installDir: string, name: ConnectorName, forgetCredentials: boolean) =>
    disconnectConnector(installDir, name, forgetCredentials),
);
ipcMain.handle("desktop:start-whatsapp-link", async (_event, installDir: string) => startWhatsAppLink(installDir));
ipcMain.handle("desktop:get-whatsapp-link-status", async (_event, installDir: string) => getWhatsAppLinkStatus(installDir));
ipcMain.handle("desktop:stop-whatsapp-link", async (_event, installDir: string) => stopWhatsAppLink(installDir));

void app.whenReady().then(async () => {
  nativeTheme.themeSource = (await readSettings()).theme;
  createWindow();
  scheduleDesktopAppUpdateCheck();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
