import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence } from "framer-motion";
import { Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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
  const [startStatus, setStartStatus] = useState<"idle" | "starting" | "started" | "failed">("idle");
  const [startError, setStartError] = useState("");

  const form = useForm<InstallForm>({
    resolver: zodResolver(installSchema),
    defaultValues: defaultInstallValues,
    mode: "onChange",
  });

  const values = form.watch();
  const steps = useMemo(() => getWizardSteps(values.sameWorker), [values.sameWorker]);
  const step = steps[Math.min(stepIndex, steps.length - 1)] ?? "location";
  const copy = useMemo(() => (key: keyof typeof messages.en) => t(language, key), [language]);

  useEffect(() => {
    void loadSettings().then((settings) => {
      setLanguage(settings.language);
      setTheme(settings.theme);
      if (settings.installDir) {
        form.setValue("installDir", settings.installDir, { shouldValidate: true });
      }
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
    void saveSettings({ language, theme, installDir: values.installDir || "" });
  }, [language, theme, values.installDir]);

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

  async function prepareInstall() {
    const ok = await form.trigger();
    if (!ok) {
      return;
    }

    setScreen("installing");
    setInstallEvents([]);
    setInstallError("");
    setSavedInstallResult(null);
    setStartStatus("idle");
    setStartError("");

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
    const installDir = savedInstallResult?.installDir || values.installDir;
    if (!window.octopalDesktop || !installDir) {
      return;
    }

    setStartStatus("starting");
    setStartError("");
    try {
      await window.octopalDesktop.startOctopal(installDir);
      setStartStatus("started");
    } catch (error) {
      setStartStatus("failed");
      setStartError(error instanceof Error ? error.message : copy("startFailed"));
    }
  }

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
            onStart={() => setScreen("wizard")}
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
            onPrepareInstall={() => void prepareInstall()}
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
            title={startStatus === "started" ? copy("octopalStarted") : copy("completeTitle")}
            body={startStatus === "failed" ? startError : ""}
            octoAlt="Octopal mascot"
            action={
              startStatus === "started" ? null : (
                <Button
                  type="button"
                  variant="success"
                  className="status-action-button"
                  disabled={startStatus === "starting"}
                  onClick={() => void startInstalledOctopal()}
                >
                  <Play data-icon="inline-start" />
                  {startStatus === "starting" ? copy("startingOctopal") : copy("startOctopal")}
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
