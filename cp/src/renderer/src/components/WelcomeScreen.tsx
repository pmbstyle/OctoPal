import { AlertTriangle, ArrowRight, CheckCircle2, Globe2, Moon, Play, RefreshCw, Settings, Sun } from "lucide-react";
import { motion } from "framer-motion";

import octoImage from "../../../../assets/octo.png";
import { languages, type Language } from "../lib/i18n";
import type { CopyFn, Theme } from "../lib/appTypes";
import { Button } from "./Button";
import { LabeledSelect } from "./LabeledSelect";

function preflightHint(copy: CopyFn, check: DesktopPrerequisiteCheck) {
  if (check.ok) {
    return copy("available");
  }

  return check.required ? copy("required") : copy("recommended");
}

export function WelcomeScreen({
  copy,
  language,
  theme,
  onLanguageChange,
  onThemeChange,
  onStart,
  onStartOctopal,
  onRefreshPrerequisites,
  installed,
  canConfigure,
  preflightChecks,
  preflightStatus,
  preflightError,
}: {
  copy: CopyFn;
  language: Language;
  theme: Theme;
  onLanguageChange: (language: Language) => void;
  onThemeChange: (theme: Theme) => void;
  onStart: () => void;
  onStartOctopal: () => void;
  onRefreshPrerequisites: () => void;
  installed: boolean;
  canConfigure: boolean;
  preflightChecks: DesktopPrerequisiteCheck[];
  preflightStatus: "idle" | "checking" | "ready" | "failed";
  preflightError: string;
}) {
  const hasBlockingIssue = preflightChecks.some((check) => check.required && !check.ok);
  const showPreflight = preflightStatus !== "idle" || preflightChecks.length > 0 || preflightError;

  return (
    <motion.section
      key="welcome"
      className="welcome-screen"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.28 }}
    >
      <div className="speech-bubble">{installed ? copy("welcomeInstalled") : copy("welcome")}</div>
      <img className="octo welcome-octo" src={octoImage} alt="Octopal mascot" />
      <div className="welcome-controls">
        <LabeledSelect
          icon={<Globe2 />}
          label={copy("language")}
          value={language}
          onChange={(next) => onLanguageChange(next as Language)}
          options={languages.map((item) => ({ value: item.value, label: item.label }))}
        />
        <LabeledSelect
          icon={theme === "dark" ? <Moon /> : <Sun />}
          label={copy("theme")}
          value={theme}
          onChange={(next) => onThemeChange(next as Theme)}
          options={[
            { value: "light", label: copy("light") },
            { value: "dark", label: copy("dark") },
            { value: "system", label: copy("system") },
          ]}
        />
      </div>
      {showPreflight ? (
        <section className="requirements-card welcome-requirements" aria-live="polite">
          <div className="requirements-head">
            <div>
              <strong>{copy("requirements")}</strong>
              <small>
                {preflightStatus === "checking"
                  ? copy("checking")
                  : hasBlockingIssue
                    ? copy("installBlocked")
                    : copy("preflightReady")}
              </small>
            </div>
            <Button type="button" variant="ghost" onClick={onRefreshPrerequisites} disabled={preflightStatus === "checking"}>
              <RefreshCw data-icon="inline-start" />
              {copy("refresh")}
            </Button>
          </div>
          {preflightError ? (
            <div className="welcome-error" role="alert">{preflightError}</div>
          ) : null}
          {preflightChecks.length > 0 ? (
            <div className="requirements-grid">
              {preflightChecks.map((check) => (
                <div className={check.ok ? "requirement requirement-ok" : "requirement requirement-missing"} key={check.id}>
                  <div className="requirement-title">
                    {check.ok ? <CheckCircle2 /> : <AlertTriangle />}
                    <strong>{check.label}</strong>
                  </div>
                  <small>{preflightHint(copy, check)}</small>
                  <p title={check.detail}>{check.detail}</p>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
      <div className={installed ? "welcome-actions" : undefined}>
        {installed ? (
          <Button
            className="welcome-button welcome-action-button"
            variant="success"
            onClick={onStartOctopal}
          >
            <Play data-icon="inline-start" />
            {copy("startOctopal")}
          </Button>
        ) : null}
        <Button
          className={installed ? "welcome-button welcome-action-button" : "welcome-button"}
          variant={installed ? "secondary" : "primary"}
          onClick={onStart}
          disabled={!installed && !canConfigure}
        >
          {installed ? <Settings data-icon="inline-start" /> : null}
          {installed ? copy("modifyConfig") : copy("configure")}
          {!installed ? <ArrowRight data-icon="inline-end" /> : null}
        </Button>
      </div>
    </motion.section>
  );
}
