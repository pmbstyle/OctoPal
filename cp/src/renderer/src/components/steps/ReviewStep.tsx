import { buildOctopalConfig, providers, searchProviders, type InstallForm } from "../../lib/install";
import type { CopyFn } from "../../lib/appTypes";
import { ReviewItem } from "../ReviewItem";
import { StepSection } from "../StepSection";

export function ReviewStep({ body, copy, values }: { body: string; copy: CopyFn; values: InstallForm }) {
  return (
    <StepSection body={body}>
      <div className="review-grid">
        <ReviewItem label={copy("installFolder")} value={values.installDir || "-"} />
        <ReviewItem label={copy("stepChannel")} value={values.channel === "telegram" ? copy("telegram") : copy("whatsapp")} />
        <ReviewItem label={copy("provider")} value={providers.find((item) => item.id === values.providerId)?.label ?? values.providerId} />
        <ReviewItem label={copy("model")} value={values.model || "-"} />
        <ReviewItem label={copy("stepWorkerLlm")} value={values.sameWorker ? copy("sameWorker") : values.workerModel || values.model || "-"} />
        <ReviewItem
          label={copy("stepTools")}
          value={
            !values.searchProvider
              ? copy("noSearch")
              : searchProviders.find((item) => item.id === values.searchProvider)?.label ?? values.searchProvider
          }
        />
      </div>
      <pre className="config-preview">{JSON.stringify(buildOctopalConfig(values), null, 2)}</pre>
    </StepSection>
  );
}
