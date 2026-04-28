import { app, BrowserWindow, dialog, ipcMain, nativeTheme, type OpenDialogOptions } from "electron";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

type DesktopSettings = {
  language: "en" | "fr" | "es" | "zh";
  theme: "light" | "dark" | "system";
  installDir: string;
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

function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 920,
    minHeight: 680,
    title: "Octopal Desktop",
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
    const { stdout, stderr } = await execFileAsync(command, args, { timeout: 5000 });
    return { ok: true, detail: (stdout || stderr).trim().split(/\r?\n/)[0] || "Available" };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unavailable";
    return { ok: false, detail: message };
  }
}

ipcMain.handle("desktop:load-settings", async () => readSettings());
ipcMain.handle("desktop:save-settings", async (_event, settings: DesktopSettings) => writeSettings(settings));

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

ipcMain.handle("desktop:check-prerequisites", async () => {
  const checks = await Promise.all([
    checkCommand("git", ["--version"]),
    checkCommand("uv", ["--version"]),
    checkCommand("docker", ["--version"]),
    checkCommand("node", ["--version"]),
  ]);

  return [
    { id: "git", label: "Git", ...checks[0] },
    { id: "uv", label: "uv", ...checks[1] },
    { id: "docker", label: "Docker", ...checks[2] },
    { id: "node", label: "Node.js", ...checks[3] },
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
  await writeFile(planPath, JSON.stringify(payload, null, 2), "utf8");
  return { planPath };
});

void app.whenReady().then(async () => {
  nativeTheme.themeSource = (await readSettings()).theme;
  createWindow();

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
