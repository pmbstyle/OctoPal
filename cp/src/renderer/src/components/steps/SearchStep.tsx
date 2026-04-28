import { motion } from "framer-motion";
import type { FieldErrors, UseFormReturn } from "react-hook-form";

import { Field, Input } from "../Field";
import { ImageLogo } from "../ImageLogo";
import { StepSection } from "../StepSection";
import { ToggleCard } from "../ToggleCard";
import type { CopyFn } from "../../lib/appTypes";
import { searchProviders, type InstallForm } from "../../lib/install";
import { searchLogos } from "../../lib/logos";

export function SearchStep({
  copy,
  values,
  form,
  errors,
  onSearchProviderToggle,
}: {
  copy: CopyFn;
  values: InstallForm;
  form: UseFormReturn<InstallForm>;
  errors: FieldErrors<InstallForm>;
  onSearchProviderToggle: (providerId: "brave" | "firecrawl") => void;
}) {
  return (
    <StepSection body={copy("toolsBody")}>
      <div className="choice-grid search-grid">
        {searchProviders.map((provider) => (
          <ToggleCard
            key={provider.id}
            active={values.searchProvider === provider.id}
            icon={<ImageLogo src={searchLogos[provider.id]} alt="" />}
            title={provider.label}
            body={`${provider.label} ${copy("apiKey")}`}
            onClick={() => onSearchProviderToggle(provider.id)}
          />
        ))}
      </div>
      {values.searchProvider === "brave" ? (
        <motion.div className="single-field reveal-form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Field label={copy("braveKey")} hint={copy("required")} invalid={!!errors.braveApiKey}>
            <Input {...form.register("braveApiKey")} type="password" />
          </Field>
        </motion.div>
      ) : null}
      {values.searchProvider === "firecrawl" ? (
        <motion.div className="single-field reveal-form" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Field label={copy("firecrawlKey")} hint={copy("required")} invalid={!!errors.firecrawlApiKey}>
            <Input {...form.register("firecrawlApiKey")} type="password" />
          </Field>
        </motion.div>
      ) : null}
    </StepSection>
  );
}
