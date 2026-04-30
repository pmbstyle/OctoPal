import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence } from "framer-motion";
import { Play, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { AppShell } from "./components/AppShell";
import { Button } from "./components/Button";
import { InstallProgressScreen } from "./components/InstallProgressScreen";
import { StatusScreen } from "./components/StatusScreen";
import { WelcomeScreen } from "./components/WelcomeScreen";
import { WizardScreen } from "./components/WizardScreen";
import type { Screen, StepId, Theme } from "./lib/appTypes";
import {
  buildOctopalConfig,
  defaultInstallValues,
  formValuesFromOctopalConfig,
  installSchema,
  providers,
  type InstallForm,
} from "./lib/install";
import { messages, t, type Language } from "./lib/i18n";
import { getPreferredTheme, loadSettings, saveSettings } from "./lib/settings";
import { getValidationFields, getWizardSteps } from "./lib/wizard";

export function App() {
  const [language, setLanguage] = useState<Language>("en");
  const [theme, setTheme] = useState<Theme>("system");
  const [screen, setScreen] = useState<Screen>("welcome");
  const [stepIndex, setStepIndex] = useState(0);
  const [savedPlanPath, setSavedPlanPath] = useState("");
  const [savedInstallResult, setSavedInstallResult] = useState<DesktopInstallResult | null>(null);
  const [installEvents, setInstallEvents] = useState<DesktopInstallEvent[]>([]);
  const [installError, setInstallError] = useState("");
  const [startStatus, setStartStatus] = useState<"idle" | "starting" | "started" | "stopping" | "failed">("idle");
  const [startError, setStartError] = useState("");
  const [startErrorDetail, setStartErrorDetail] = useState("");
  const [runtimeStatus, setRuntimeStatus] = useState<DesktopRuntimeStatus | null>(null);
  const [configurationMode, setConfigurationMode] = useState<"install" | "edit">("install");
  const [installState, setInstallState] = useState<DesktopInstallState>({
    installed: false,
    installDir: "",
    configPath: "",
    planPath: "",
  });
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  const form = useForm<InstallForm>({
    resolver: zodResolver(installSchema),
    defaultValues: defaultInstallValues,
    mode: "onChange",
  });

  const values = form.watch();
  const steps = useMemo(() => getWizardSteps(values.sameWorker), [values.sameWorker]);
  const step = steps[Math.min(stepIndex, steps.length - 1)] ?? "location";
  const copy = useMemo(() => (key: keyof typeof messages.en) => t(language, key), [language]);
  const runtimeInstallDir = savedInstallResult?.installDir || installState.installDir || values.installDir;
  const runtimeView = useMemo(() => {
    if (startStatus === "starting") {
      return {
        state: "starting" as const,
        title: copy("octopalStarting"),
        detail: runtimeStatus?.detail || copy("octopalStartingDetail"),
      };
    }

    if (startStatus === "stopping") {
      return {
        state: "stopping" as const,
        title: copy("octopalStopping"),
        detail: runtimeStatus?.detail || copy("octopalStoppingDetail"),
      };
    }

    if (startStatus === "failed") {
      return {
        state: "error" as const,
        title: startError || runtimeStatus?.title || copy("runtimeStatusError"),
        detail: startErrorDetail || runtimeStatus?.detail || "",
      };
    }

    if (runtimeStatus) {
      return {
        state: runtimeStatus.state,
        title: runtimeStatus.title,
        detail: runtimeStatus.detail,
      };
    }

    if (installState.installed) {
      return {
        state: "checking" as const,
        title: copy("octopalStatusChecking"),
        detail: "",
      };
    }

    return {
      state: "stopped" as const,
      title: copy("octopalStopped"),
      detail: copy("octopalStoppedDetail"),
    };
  }, [copy, installState.installed, runtimeStatus, startError, startErrorDetail, startStatus]);

  const refreshRuntimeStatus = useCallback(async () => {
    if (!window.octopalDesktop || !installState.installed || !runtimeInstallDir) {
      return;
    }

    const result = await window.octopalDesktop.getOctopalStatus(runtimeInstallDir);
    setRuntimeStatus(result);
    setStartStatus((current) => {
      if (!result.ok || result.state === "error") {
        return "failed";
      }

      if (result.state === "running") {
        return "started";
      }

      if (result.state === "stopped") {
        return current === "starting" ? current : "idle";
      }

      return current;
    });

    if (!result.ok || result.state === "error") {
      setStartError(result.title);
      setStartErrorDetail(result.detail);
      return;
    }

    setStartError("");
    setStartErrorDetail("");
  }, [installState.installed, runtimeInstallDir]);

  useEffect(() => {
    void loadSettings().then(async (settings) => {
      setLanguage(settings.language);
      setTheme(settings.theme);
      if (settings.installDir) {
        form.setValue("installDir", settings.installDir, { shouldValidate: true });
      }
      if (window.octopalDesktop) {
        setInstallState(await window.octopalDesktop.getInstallState());
      }
      setSettingsLoaded(true);
    });
  }, [form]);

  useEffect(() => {
    document.documentElement.dataset.theme = getPreferredTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (theme !== "system") {
      return;
    }

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const updateSystemTheme = () => {
      document.documentElement.dataset.theme = media.matches ? "dark" : "light";
    };

    media.addEventListener("change", updateSystemTheme);
    return () => media.removeEventListener("change", updateSystemTheme);
  }, [theme]);

  useEffect(() => {
    if (!settingsLoaded) {
      return;
    }

    void saveSettings({ language, theme, installDir: values.installDir || "" });
  }, [language, settingsLoaded, theme, values.installDir]);

  useEffect(() => {
    if (!settingsLoaded || !installState.installed) {
      return;
    }

    void refreshRuntimeStatus();
    const interval = window.setInterval(() => {
      void refreshRuntimeStatus();
    }, 5000);

    return () => window.clearInterval(interval);
  }, [installState.installed, refreshRuntimeStatus, settingsLoaded]);

  useEffect(() => {
    setStepIndex((current) => Math.min(current, steps.length - 1));
  }, [steps.length]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0 });
    document.querySelector(".setup-content")?.scrollTo({ top: 0, left: 0 });
  }, [stepIndex, step]);

  function updateLanguage(next: Language) {
    setLanguage(next);
    document.documentElement.lang = next;
  }

  function updateProvider(providerId: string, target: "octo" | "worker") {
    const provider = providers.find((item) => item.id === providerId);
    if (target === "octo") {
      form.setValue("providerId", providerId, { shouldValidate: true });
      if (provider?.model) {
        form.setValue("model", provider.model, { shouldValidate: true });
      }
      return;
    }

    form.setValue("workerProviderId", providerId, { shouldValidate: true });
    if (provider?.model) {
      form.setValue("workerModel", provider.model, { shouldValidate: true });
    }
  }

  function toggleSearchProvider(providerId: "brave" | "firecrawl") {
    const nextProvider = values.searchProvider === providerId ? undefined : providerId;
    form.setValue("searchProvider", nextProvider, { shouldDirty: true, shouldValidate: true });
    if (!nextProvider) {
      form.clearErrors(["searchProvider", "braveApiKey", "firecrawlApiKey"]);
    }
  }

  async function chooseInstallDir() {
    try {
      const selected = window.octopalDesktop ? await window.octopalDesktop.chooseInstallDir() : "C:\\Octopal";
      if (selected) {
        form.setValue("installDir", selected, { shouldDirty: true, shouldValidate: true });
      }
    } catch (error) {
      console.error("Unable to choose install folder", error);
    }
  }

  function controlWindow(action: "close" | "minimize" | "maximize") {
    if (!window.octopalDesktop) {
      return;
    }

    if (action === "close") {
      void window.octopalDesktop.closeWindow();
      return;
    }

    if (action === "minimize") {
      void window.octopalDesktop.minimizeWindow();
      return;
    }

    void window.octopalDesktop.toggleMaximizeWindow();
  }

  async function nextStep() {
    const ok = await form.trigger(getValidationFields(step as StepId, values));
    if (!ok) {
      return;
    }
    setStepIndex((current) => Math.min(current + 1, steps.length - 1));
  }

  function previousStep() {
    if (stepIndex === 0) {
      setScreen("welcome");
      return;
    }
    setStepIndex((current) => Math.max(current - 1, 0));
  }

  async function openConfiguration() {
    const installDir = installState.installDir || values.installDir;
    if (window.octopalDesktop && installState.installed && installDir) {
      try {
        const config = await window.octopalDesktop.loadOctopalConfig();
        form.reset(formValuesFromOctopalConfig(config, installDir));
        setConfigurationMode("edit");
      } catch (error) {
        console.error("Unable to load installed Octopal config", error);
        setConfigurationMode("install");
      }
    } else {
      setConfigurationMode("install");
    }

    setStepIndex(0);
    setScreen("wizard");
  }

  async function saveConfiguration() {
    const ok = await form.trigger();
    if (!ok || !window.octopalDesktop) {
      return;
    }

    try {
      const nextState = await window.octopalDesktop.saveOctopalConfig(buildOctopalConfig(values));
      setInstallState(nextState);
      setSavedInstallResult(null);
      setSavedPlanPath("");
      setRuntimeStatus(null);
      setStartStatus("idle");
      setStartError("");
      setStartErrorDetail("");
      setScreen("welcome");
    } catch (error) {
      setInstallError(error instanceof Error ? error.message : copy("installFailedBody"));
      setScreen("failed");
    }
  }

  async function submitReview() {
    if (configurationMode === "edit") {
      await saveConfiguration();
      return;
    }

    await prepareInstall();
  }

  async function prepareInstall() {
    const ok = await form.trigger();
    if (!ok) {
      return;
    }

    setScreen("installing");
    setInstallEvents([]);
    setInstallError("");
    setSavedInstallResult(null);
    setRuntimeStatus(null);
    setStartStatus("idle");
    setStartError("");
    setStartErrorDetail("");

    const payload = {
      createdBy: "Octopal Desktop",
      createdAt: new Date().toISOString(),
      installDir: values.installDir,
      octopalConfig: buildOctopalConfig(values),
    };

    if (window.octopalDesktop) {
      const unsubscribe = window.octopalDesktop.onInstallEvent((event) => {
        setInstallEvents((current) => [...current, event].slice(-80));
      });

      try {
        const result = await window.octopalDesktop.installOctopal(payload);
        setSavedInstallResult(result);
        setSavedPlanPath(result.planPath);
        setInstallState({
          installed: true,
          installDir: result.installDir,
          configPath: result.configPath,
          planPath: result.planPath,
        });
        setScreen("done");
      } catch (error) {
        const message = error instanceof Error ? error.message : copy("installFailedBody");
        setInstallError(message);
        setScreen("failed");
      } finally {
        unsubscribe();
      }
    } else {
      setSavedPlanPath("browser-preview/.octopal-desktop/install-plan.json");
      setInstallEvents([{ kind: "done", message: "Browser preview", detail: "Electron installer API is not available." }]);
      window.setTimeout(() => setScreen("done"), 850);
    }
  }

  async function startInstalledOctopal() {
    const installDir = savedInstallResult?.installDir || installState.installDir || values.installDir;
    if (!window.octopalDesktop || !installDir) {
      return;
    }

    setStartStatus("starting");
    setStartError("");
    setStartErrorDetail("");
    try {
      const result = await window.octopalDesktop.startOctopal(installDir);
      if (!result.ok) {
        setStartStatus("failed");
        setStartError(result.error || copy("startFailed"));
        setStartErrorDetail(result.detail);
        return;
      }
      setStartStatus("started");
      void refreshRuntimeStatus();
    } catch (error) {
      setStartStatus("failed");
      setStartError(error instanceof Error ? error.message : copy("startFailed"));
      setStartErrorDetail("");
    }
  }

  async function stopInstalledOctopal() {
    const installDir = savedInstallResult?.installDir || installState.installDir || values.installDir;
    if (!window.octopalDesktop || !installDir) {
      return;
    }

    setStartStatus("stopping");
    setStartError("");
    setStartErrorDetail("");
    try {
      const result = await window.octopalDesktop.stopOctopal(installDir);
      if (!result.ok) {
        setStartStatus("failed");
        setStartError(result.error || copy("stopFailed"));
        setStartErrorDetail(result.detail);
        return;
      }
      setStartStatus("idle");
      void refreshRuntimeStatus();
    } catch (error) {
      setStartStatus("failed");
      setStartError(error instanceof Error ? error.message : copy("stopFailed"));
      setStartErrorDetail("");
    }
  }

  const doneTitle = startStatus === "idle" && !runtimeStatus ? copy("completeTitle") : runtimeView.title;
  const doneBody = runtimeView.state === "error" || (startStatus === "idle" && !runtimeStatus) ? "" : runtimeView.detail;
  const doneCanStop = runtimeView.state === "running" || runtimeView.state === "stopping";
  const doneBusy = runtimeView.state === "starting" || runtimeView.state === "stopping";

  return (
    <AppShell
      title={copy("appTitle")}
      onClose={() => controlWindow("close")}
      onMinimize={() => controlWindow("minimize")}
      onMaximize={() => controlWindow("maximize")}
    >
      <AnimatePresence mode="wait">
        {screen === "welcome" ? (
          <WelcomeScreen
            key="welcome"
            copy={copy}
            language={language}
            theme={theme}
            onLanguageChange={updateLanguage}
            onThemeChange={setTheme}
            onStart={() => void openConfiguration()}
            onStartOctopal={() => void startInstalledOctopal()}
            onStopOctopal={() => void stopInstalledOctopal()}
            installed={installState.installed}
            runtimeState={runtimeView.state}
            runtimeTitle={runtimeView.title}
            runtimeDetail={runtimeView.detail}
          />
        ) : null}

        {screen === "wizard" ? (
          <WizardScreen
            key={step}
            copy={copy}
            language={language}
            theme={theme}
            step={step}
            stepIndex={stepIndex}
            totalSteps={steps.length}
            values={values}
            form={form}
            errors={form.formState.errors}
            onLanguageChange={updateLanguage}
            onThemeChange={setTheme}
            onChooseInstallDir={() => void chooseInstallDir()}
            onProviderChange={updateProvider}
            onSearchProviderToggle={toggleSearchProvider}
            onBack={previousStep}
            onNext={() => void nextStep()}
            onPrepareInstall={() => void submitReview()}
            reviewBody={configurationMode === "edit" ? copy("reviewBodyEdit") : copy("reviewBody")}
            reviewActionLabel={configurationMode === "edit" ? copy("saveConfiguration") : copy("startInstall")}
          />
        ) : null}

        {screen === "installing" ? (
          <InstallProgressScreen
            key="installing"
            title={copy("installingTitle")}
            body={copy("installingBody")}
            events={installEvents}
            busy
          />
        ) : null}

        {screen === "done" ? (
          <StatusScreen
            key="done"
            title={doneTitle}
            body={doneBody}
            octoAlt="Octopal mascot"
            errorTitle={runtimeView.state === "error" ? runtimeView.title : ""}
            errorDetail={runtimeView.state === "error" ? runtimeView.detail : ""}
            action={
              doneCanStop ? (
                <Button
                  type="button"
                  variant="danger"
                  className="status-action-button"
                  disabled={doneBusy}
                  onClick={() => void stopInstalledOctopal()}
                >
                  <Square data-icon="inline-start" />
                  {runtimeView.state === "stopping" ? copy("stoppingOctopal") : copy("stopOctopal")}
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="success"
                  className="status-action-button"
                  disabled={doneBusy}
                  onClick={() => void startInstalledOctopal()}
                >
                  <Play data-icon="inline-start" />
                  {runtimeView.state === "starting" ? copy("startingOctopal") : copy("startOctopal")}
                </Button>
              )
            }
          />
        ) : null}

        {screen === "failed" ? (
          <InstallProgressScreen
            key="failed"
            title={copy("installFailedTitle")}
            body={copy("installFailedBody")}
            events={installEvents}
            error={installError}
          />
        ) : null}
      </AnimatePresence>
    </AppShell>
  );
}
