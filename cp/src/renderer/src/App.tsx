import { zodResolver } from "@hookform/resolvers/zod";
import { AnimatePresence } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { AppShell } from "./components/AppShell";
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
    const payload = {
      createdBy: "Octopal Desktop",
      createdAt: new Date().toISOString(),
      installDir: values.installDir,
      octopalConfig: buildOctopalConfig(values),
    };

    if (window.octopalDesktop) {
      const result = await window.octopalDesktop.writeInstallPlan(payload);
      setSavedPlanPath(result.planPath);
    } else {
      setSavedPlanPath("browser-preview/.octopal-desktop/install-plan.json");
    }

    window.setTimeout(() => setScreen("done"), 850);
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
          <StatusScreen
            key="installing"
            title={copy("installingTitle")}
            body={copy("installingBody")}
            octoAlt="Octopal mascot"
            busy
          />
        ) : null}

        {screen === "done" ? (
          <StatusScreen
            key="done"
            title={copy("completeTitle")}
            body={`${copy("completeBody")} ${savedPlanPath ? `${copy("planSaved")}: ${savedPlanPath}` : ""}`}
            octoAlt="Octopal mascot"
          />
        ) : null}
      </AnimatePresence>
    </AppShell>
  );
}
