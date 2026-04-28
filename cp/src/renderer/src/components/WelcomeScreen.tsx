import { ArrowRight, Globe2, Moon, Sun } from "lucide-react";
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
}: {
  copy: CopyFn;
  language: Language;
  theme: Theme;
  onLanguageChange: (language: Language) => void;
  onThemeChange: (theme: Theme) => void;
  onStart: () => void;
}) {
  return (
    <motion.section
      key="welcome"
      className="welcome-screen"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.28 }}
    >
      <div className="speech-bubble">{copy("welcome")}</div>
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
      <Button className="welcome-button" onClick={onStart}>
        {copy("configure")}
        <ArrowRight data-icon="inline-end" />
      </Button>
    </motion.section>
  );
}
