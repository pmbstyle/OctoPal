import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readdir, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { delimiter, dirname, join } from "node:path";

const REPO_URL = "https://github.com/pmbstyle/Octopal.git";
const LATEST_RELEASE_API_URL = "https://api.github.com/repos/pmbstyle/Octopal/releases/latest";

export type InstallEvent = {
  kind: "step" | "log" | "warning" | "error" | "done";
  message: string;
  detail?: string;
};

export type InstallPayload = {
  createdBy: string;
  createdAt: string;
  installDir: string;
  octopalConfig: unknown;
};

export type InstallResult = {
  installDir: string;
  releaseTag: string;
  configPath: string;
  planPath: string;
};

export type StartResult = {
  ok: true;
  installDir: string;
  detail: string;
};

export type StartFailure = {
  ok: false;
  error: string;
  detail: string;
};

export type StopResult = {
  ok: true;
  installDir: string;
  detail: string;
};

export type StopFailure = {
  ok: false;
  error: string;
  detail: string;
};

type CommandResult = {
  stdout: string;
  stderr: string;
};

type RunOptions = {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  quiet?: boolean;
};

type DetachedStartResult = {
  stdout: string;
  stderr: string;
  exited: boolean;
  code: number | null;
};

function sanitizeOutput(text: string): string {
  return text
    .replace(/\b\d{7,12}:[A-Za-z0-9_-]{20,}\b/g, "[redacted-token]")
    .replace(/\bsk-or-v1-[A-Za-z0-9_-]{16,}\b/g, "[redacted-key]")
    .replace(/\bsk-[A-Za-z0-9_-]{16,}\b/g, "[redacted-key]")
    .replace(/\bBS[A-Za-z0-9_-]{20,}\b/g, "[redacted-key]")
    .replace(
      /((?:api[_-]?key|bot[_-]?token|callback[_-]?token|telegram[_-]?bot[_-]?token|secret|token)\s*=\s*')[^']*(')/gi,
      "$1[redacted]$2",
    )
    .replace(
      /((?:api[_-]?key|bot[_-]?token|callback[_-]?token|telegram[_-]?bot[_-]?token|secret|token)"?\s*:\s*")[^"]*(")/gi,
      "$1[redacted]$2",
    );
}

function withPythonDesktopEnv(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  return {
    ...withLocalToolPaths(env),
    FORCE_COLOR: "0",
    NO_COLOR: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONUTF8: "1",
  };
}

function emitStep(emit: (event: InstallEvent) => void, message: string, detail?: string) {
  emit({ kind: "step", message, detail });
}

function emitWarning(emit: (event: InstallEvent) => void, message: string, detail?: string) {
  emit({ kind: "warning", message, detail });
}

function getPathValue(env: NodeJS.ProcessEnv): string {
  return env.Path ?? env.PATH ?? "";
}

function withLocalToolPaths(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const home = homedir();
  const extraPaths =
    process.platform === "win32"
      ? [join(home, ".local", "bin"), join(home, ".cargo", "bin")]
      : [join(home, ".local", "bin"), join(home, ".cargo", "bin")];
  const pathKey = process.platform === "win32" ? "Path" : "PATH";
  return {
    ...env,
    [pathKey]: [...extraPaths, getPathValue(env)].filter(Boolean).join(delimiter),
  };
}

function getUvCandidates(): string[] {
  const home = homedir();
  return process.platform === "win32"
    ? [join(home, ".local", "bin", "uv.exe"), join(home, ".cargo", "bin", "uv.exe")]
    : [join(home, ".local", "bin", "uv"), join(home, ".cargo", "bin", "uv")];
}

function runCommand(
  command: string,
  args: string[],
  emit: (event: InstallEvent) => void,
  options: RunOptions = {},
): Promise<CommandResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env ?? withLocalToolPaths(),
      shell: false,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk: Buffer) => {
      const text = sanitizeOutput(chunk.toString());
      stdout += text;
      if (!options.quiet) {
        emit({ kind: "log", message: text.trim() });
      }
    });

    child.stderr?.on("data", (chunk: Buffer) => {
      const text = sanitizeOutput(chunk.toString());
      stderr += text;
      if (!options.quiet) {
        emit({ kind: "log", message: text.trim() });
      }
    });

    child.on("error", (error) => reject(error));
    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
        return;
      }
      reject(new Error(`${command} ${args.join(" ")} exited with code ${code}: ${sanitizeOutput(stderr || stdout).trim()}`));
    });
  });
}

function runDetachedStart(command: string, args: string[], options: RunOptions = {}): Promise<DetachedStartResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      detached: true,
      env: options.env ?? withPythonDesktopEnv(),
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const finish = (result: DetachedStartResult) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };

    const timer = setTimeout(() => {
      child.unref();
      finish({ stdout, stderr, exited: false, code: null });
    }, 3500);

    child.stdout?.on("data", (chunk: Buffer) => {
      stdout += sanitizeOutput(chunk.toString());
    });

    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += sanitizeOutput(chunk.toString());
    });

    child.on("error", (error) => {
      if (!settled) {
        clearTimeout(timer);
        reject(error);
      }
    });

    child.on("close", (code) => {
      finish({ stdout, stderr, exited: true, code });
    });
  });
}

async function commandExists(command: string, emit: (event: InstallEvent) => void): Promise<boolean> {
  try {
    await runCommand(command, ["--version"], emit, { quiet: true });
    return true;
  } catch {
    return false;
  }
}

async function resolveUv(emit: (event: InstallEvent) => void): Promise<string | null> {
  if (await commandExists("uv", emit)) {
    return "uv";
  }

  return getUvCandidates().find((candidate) => existsSync(candidate)) ?? null;
}

async function ensureUv(emit: (event: InstallEvent) => void): Promise<string> {
  const existingUv = await resolveUv(emit);
  if (existingUv) {
    return existingUv;
  }

  emitStep(emit, "Installing uv");
  if (process.platform === "win32") {
    await runCommand(
      "powershell.exe",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"],
      emit,
    );
  } else {
    await runCommand("sh", ["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], emit);
  }

  const installedUv = await resolveUv(emit);
  if (!installedUv) {
    throw new Error("uv was installed, but it is not available on PATH yet. Restart the app or add uv to PATH.");
  }
  return installedUv;
}

async function getLatestReleaseTag(emit: (event: InstallEvent) => void): Promise<string> {
  emitStep(emit, "Resolving latest Octopal release");
  try {
    const response = await fetch(LATEST_RELEASE_API_URL, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "octopal-desktop-installer",
      },
    });
    if (response.ok) {
      const release = (await response.json()) as { tag_name?: string };
      if (release.tag_name) {
        return release.tag_name.trim();
      }
    }
  } catch {
    // Fall back to git tags below.
  }

  const { stdout } = await runCommand(
    "git",
    ["ls-remote", "--tags", "--sort=-version:refname", "--refs", REPO_URL],
    emit,
    { quiet: true },
  );
  const firstTag = stdout
    .split(/\r?\n/)
    .map((line) => line.match(/refs\/tags\/(.+)$/)?.[1])
    .find(Boolean);

  if (!firstTag) {
    throw new Error("Could not determine the latest Octopal release tag.");
  }
  return firstTag;
}

async function isDirectoryEmpty(path: string): Promise<boolean> {
  try {
    const entries = await readdir(path);
    return entries.length === 0;
  } catch {
    return true;
  }
}

async function pathExists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function cloneOrCheckoutRelease(installDir: string, releaseTag: string, emit: (event: InstallEvent) => void) {
  const exists = await pathExists(installDir);
  const hasGit = existsSync(join(installDir, ".git"));
  const hasProject = existsSync(join(installDir, "pyproject.toml"));

  if (!exists || (await isDirectoryEmpty(installDir))) {
    await mkdir(dirname(installDir), { recursive: true });
    emitStep(emit, `Downloading Octopal ${releaseTag}`, installDir);
    await runCommand(
      "git",
      ["-c", "advice.detachedHead=false", "clone", "--branch", releaseTag, "--depth", "1", REPO_URL, installDir],
      emit,
    );
    return;
  }

  if (hasGit && hasProject) {
    emitStep(emit, `Checking out Octopal ${releaseTag}`, installDir);
    await runCommand("git", ["fetch", "--tags", "--force"], emit, { cwd: installDir });
    await runCommand("git", ["-c", "advice.detachedHead=false", "checkout", releaseTag], emit, { cwd: installDir });
    return;
  }

  throw new Error("Install folder is not empty and does not look like an Octopal checkout.");
}

async function writeInstallFiles(payload: InstallPayload, releaseTag: string, emit: (event: InstallEvent) => void): Promise<Pick<InstallResult, "configPath" | "planPath">> {
  emitStep(emit, "Writing config.json");
  const configPath = join(payload.installDir, "config.json");
  await writeFile(configPath, JSON.stringify(payload.octopalConfig, null, 2), "utf8");

  const planDir = join(payload.installDir, ".octopal-desktop");
  await mkdir(planDir, { recursive: true });
  const planPath = join(planDir, "install-plan.json");
  await writeFile(
    planPath,
    JSON.stringify(
      {
        createdBy: payload.createdBy,
        createdAt: payload.createdAt,
        installDir: payload.installDir,
        releaseTag,
        configPath,
      },
      null,
      2,
    ),
    "utf8",
  );

  return { configPath, planPath };
}

async function installProject(installDir: string, uvCommand: string, emit: (event: InstallEvent) => void) {
  emitStep(emit, "Installing Python dependencies");
  await runCommand(uvCommand, ["sync"], emit, { cwd: installDir, env: withLocalToolPaths() });

  emitStep(emit, "Installing browser runtime");
  await runCommand(uvCommand, ["run", "playwright", "install", "chromium"], emit, {
    cwd: installDir,
    env: withLocalToolPaths(),
  });
}

async function installOptionalBridge(installDir: string, emit: (event: InstallEvent) => void) {
  const bridgeDir = join(installDir, "scripts", "whatsapp_bridge");
  if (!existsSync(bridgeDir)) {
    return;
  }

  if (!(await commandExists("npm", emit))) {
    emitWarning(emit, "npm was not found", "WhatsApp bridge dependencies were not installed.");
    return;
  }

  emitStep(emit, "Installing WhatsApp bridge dependencies");
  await runCommand("npm", ["install"], emit, { cwd: bridgeDir });
}

async function checkDocker(emit: (event: InstallEvent) => void) {
  if (!(await commandExists("docker", emit))) {
    emitWarning(emit, "Docker was not found", "Workers need Docker by default. Install Docker Desktop before running workers.");
  }
}

export async function runInstall(payload: InstallPayload, emit: (event: InstallEvent) => void): Promise<InstallResult> {
  if (!payload.installDir) {
    throw new Error("Install directory is not selected.");
  }

  emitStep(emit, "Checking Git");
  if (!(await commandExists("git", emit))) {
    throw new Error("Git is required to install Octopal. Install Git and try again.");
  }

  const releaseTag = await getLatestReleaseTag(emit);
  await cloneOrCheckoutRelease(payload.installDir, releaseTag, emit);
  const files = await writeInstallFiles(payload, releaseTag, emit);
  const uvCommand = await ensureUv(emit);
  await installProject(payload.installDir, uvCommand, emit);
  await installOptionalBridge(payload.installDir, emit);
  await checkDocker(emit);

  const result: InstallResult = {
    installDir: payload.installDir,
    releaseTag,
    ...files,
  };
  emit({ kind: "done", message: "Octopal installation is ready", detail: payload.installDir });
  return result;
}

export async function startOctopal(installDir: string): Promise<StartResult> {
  if (!installDir) {
    throw new Error("Install directory is not selected.");
  }

  if (!existsSync(join(installDir, "pyproject.toml"))) {
    throw new Error("Install folder does not look like an Octopal checkout.");
  }

  const uvCommand = await resolveUv(() => undefined);
  if (!uvCommand) {
    throw new Error("uv is not available. Install uv or run the installer again.");
  }

  const result = await runDetachedStart(uvCommand, ["run", "octopal", "start"], {
    cwd: installDir,
    env: withPythonDesktopEnv(),
    quiet: true,
  });

  if (result.exited && result.code !== 0) {
    throw new Error(
      `${uvCommand} run octopal start exited with code ${result.code}: ${sanitizeOutput(result.stderr || result.stdout).trim()}`,
    );
  }

  return {
    ok: true,
    installDir,
    detail: sanitizeOutput(result.stdout || result.stderr).trim(),
  };
}

export async function startOctopalSafely(installDir: string): Promise<StartResult | StartFailure> {
  try {
    return await startOctopal(installDir);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not start Octopal.";
    return {
      ok: false,
      error: "Could not start Octopal.",
      detail: sanitizeOutput(message),
    };
  }
}

export async function stopOctopal(installDir: string): Promise<StopResult> {
  if (!installDir) {
    throw new Error("Install directory is not selected.");
  }

  if (!existsSync(join(installDir, "pyproject.toml"))) {
    throw new Error("Install folder does not look like an Octopal checkout.");
  }

  const uvCommand = await resolveUv(() => undefined);
  if (!uvCommand) {
    throw new Error("uv is not available. Install uv or run the installer again.");
  }

  const { stdout, stderr } = await runCommand(uvCommand, ["run", "octopal", "stop"], () => undefined, {
    cwd: installDir,
    env: withPythonDesktopEnv(),
    quiet: true,
  });

  return {
    ok: true,
    installDir,
    detail: sanitizeOutput(stdout || stderr).trim(),
  };
}

export async function stopOctopalSafely(installDir: string): Promise<StopResult | StopFailure> {
  try {
    return await stopOctopal(installDir);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not stop Octopal.";
    return {
      ok: false,
      error: "Could not stop Octopal.",
      detail: sanitizeOutput(message),
    };
  }
}
