import { ArrowRight, Globe2, Moon, Play, Settings, Square, Sun } from "lucide-react";
import { motion } from "framer-motion";

import octoImage from "../../../../assets/octo.png";
import { languages, type Language } from "../lib/i18n";
import type { CopyFn, Theme } from "../lib/appTypes";
import { Button } from "./Button";
import { LabeledSelect } from "./LabeledSelect";

export function WelcomeScreen({
  copy,
  language,
  theme,
  onLanguageChange,
  onThemeChange,
  onStart,
  onStartOctopal,
  onStopOctopal,
  installed,
  runtimeState,
  runtimeTitle,
  runtimeDetail,
}: {
  copy: CopyFn;
  language: Language;
  theme: Theme;
  onLanguageChange: (language: Language) => void;
  onThemeChange: (theme: Theme) => void;
  onStart: () => void;
  onStartOctopal: () => void;
  onStopOctopal: () => void;
  installed: boolean;
  runtimeState: "checking" | "starting" | "running" | "stopping" | "stopped" | "error";
  runtimeTitle: string;
  runtimeDetail: string;
}) {
  const running = runtimeState === "running";
  const stopping = runtimeState === "stopping";
  const starting = runtimeState === "starting";
  const canStop = running || stopping;

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
      <div className={installed ? "welcome-actions" : undefined}>
        {installed ? (
          <Button
            className="welcome-button welcome-action-button"
            variant={canStop ? "danger" : "success"}
            disabled={starting || stopping}
            onClick={canStop ? onStopOctopal : onStartOctopal}
          >
            {canStop ? <Square data-icon="inline-start" /> : <Play data-icon="inline-start" />}
            {running
              ? copy("stopOctopal")
              : stopping
                ? copy("stoppingOctopal")
                : starting
                  ? copy("startingOctopal")
                  : copy("startOctopal")}
          </Button>
        ) : null}
        <Button className={installed ? "welcome-button welcome-action-button" : "welcome-button"} variant={installed ? "secondary" : "primary"} onClick={onStart}>
          {installed ? <Settings data-icon="inline-start" /> : null}
          {installed ? copy("modifyConfig") : copy("configure")}
          {!installed ? <ArrowRight data-icon="inline-end" /> : null}
        </Button>
      </div>
      {installed ? (
        <div className={`runtime-status runtime-status-${runtimeState}`} role={runtimeState === "error" ? "alert" : "status"}>
          <span className="runtime-status-dot" aria-hidden="true" />
          <div>
            <strong>{runtimeTitle}</strong>
            {runtimeDetail ? <p>{runtimeDetail}</p> : null}
          </div>
        </div>
      ) : null}
    </motion.section>
  );
}
