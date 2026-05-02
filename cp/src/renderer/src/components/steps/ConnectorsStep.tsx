import { AlertCircle, CalendarDays, CheckCircle2, Folder, Github, Info, KeyRound, Mail } from "lucide-react";
import type { FieldErrors, UseFormReturn } from "react-hook-form";

import { Button } from "../Button";
import { Field, Input } from "../Field";
import { StepSection } from "../StepSection";
import { ToggleCard } from "../ToggleCard";
import type { CopyFn } from "../../lib/appTypes";
import { cn } from "../../lib/cn";
import { connectorProviders, isExistingSecret, type InstallForm } from "../../lib/install";

type ConnectorStatus = {
  status?: string;
  message?: string;
  services?: string[];
};

function statusFor(statuses: DesktopConnectorStatusResult | null, name: "google" | "github"): ConnectorStatus | null {
  const raw = statuses?.connectors[name];
  return raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as ConnectorStatus) : null;
}

function serviceIcon(serviceId: string) {
  if (serviceId === "gmail") {
    return <Mail />;
  }
  if (serviceId === "calendar") {
    return <CalendarDays />;
  }
  if (serviceId === "drive") {
    return <Folder />;
  }
  return <Github />;
}

function ConnectorStatusLine({
  status,
  fallback,
}: {
  status: ConnectorStatus | null;
  fallback: string;
}) {
  if (!status) {
    return (
      <div className="connector-status-line connector-status-info">
        <Info />
        <span>{fallback}</span>
      </div>
    );
  }

  const tone = status.status === "ready" ? "ready" : status.status === "needs_auth" || status.status === "needs_reauth" ? "warning" : "info";
  const Icon = tone === "ready" ? CheckCircle2 : tone === "warning" ? AlertCircle : Info;

  return (
    <div className={cn("connector-status-line", `connector-status-${tone}`)}>
      <Icon />
      <span className="connector-status-badge">{status.status ?? "unknown"}</span>
      <span>{status.message || fallback}</span>
    </div>
  );
}

export function ConnectorsStep({
  copy,
  values,
  form,
  errors,
  connectorStatus,
  connectorBusy,
  connectorMessage,
  connectorMessageTone,
  canAuthorizeConnectors,
  onConnectorToggle,
  onConnectorServiceToggle,
  onAuthorizeConnector,
}: {
  copy: CopyFn;
  values: InstallForm;
  form: UseFormReturn<InstallForm>;
  errors: FieldErrors<InstallForm>;
  connectorStatus: DesktopConnectorStatusResult | null;
  connectorBusy: DesktopConnectorName | null;
  connectorMessage: string;
  connectorMessageTone: "success" | "error" | "info";
  canAuthorizeConnectors: boolean;
  onConnectorToggle: (name: DesktopConnectorName) => void;
  onConnectorServiceToggle: (name: DesktopConnectorName, serviceId: string) => void;
  onAuthorizeConnector: (name: DesktopConnectorName) => void;
}) {
  const googleStatus = statusFor(connectorStatus, "google");
  const githubStatus = statusFor(connectorStatus, "github");

  return (
    <StepSection body={copy("connectorsBody")}>
      <div className="choice-grid connectors-grid">
        <ToggleCard
          active={values.googleConnectorEnabled}
          icon={<Mail />}
          title={copy("googleConnector")}
          body={copy("googleConnectorBody")}
          onClick={() => onConnectorToggle("google")}
        />
        <ToggleCard
          active={values.githubConnectorEnabled}
          icon={<Github />}
          title={copy("githubConnector")}
          body={copy("githubConnectorBody")}
          onClick={() => onConnectorToggle("github")}
        />
      </div>

      {values.googleConnectorEnabled ? (
        <section className="connector-panel reveal-form">
          <div className="connector-panel-head">
            <strong>{copy("googleConnector")}</strong>
            <Button
              type="button"
              variant="secondary"
              disabled={!canAuthorizeConnectors || connectorBusy === "google"}
              onClick={() => onAuthorizeConnector("google")}
            >
              <KeyRound data-icon="inline-start" />
              {connectorBusy === "google" ? copy("authorizingConnector") : copy("authorizeConnector")}
            </Button>
          </div>
          <div className="connector-services" aria-label={copy("connectorServices")}>
            {connectorProviders[0].services.map((service) => (
              <label key={service.id} className="service-checkbox">
                <input
                  checked={values.googleConnectorServices.includes(service.id)}
                  type="checkbox"
                  onChange={() => onConnectorServiceToggle("google", service.id)}
                />
                <span>{serviceIcon(service.id)}</span>
                {service.label}
              </label>
            ))}
          </div>
          <div className="connector-form">
            <Field label={copy("googleClientId")} invalid={!!errors.googleClientId}>
              <Input {...form.register("googleClientId")} />
            </Field>
            <Field
              label={copy("googleClientSecret")}
              hint={isExistingSecret(values.googleClientSecret) ? copy("configured") : copy("required")}
              invalid={!!errors.googleClientSecret}
            >
              <Input {...form.register("googleClientSecret")} type="password" />
            </Field>
          </div>
          <ConnectorStatusLine status={googleStatus} fallback={copy("connectorStatusUnavailable")} />
        </section>
      ) : null}

      {values.githubConnectorEnabled ? (
        <section className="connector-panel reveal-form">
          <div className="connector-panel-head">
            <strong>{copy("githubConnector")}</strong>
            <Button
              type="button"
              variant="secondary"
              disabled={!canAuthorizeConnectors || connectorBusy === "github"}
              onClick={() => onAuthorizeConnector("github")}
            >
              <KeyRound data-icon="inline-start" />
              {connectorBusy === "github" ? copy("authorizingConnector") : copy("authorizeConnector")}
            </Button>
          </div>
          <div className="connector-services" aria-label={copy("connectorServices")}>
            {connectorProviders[1].services.map((service) => (
              <label key={service.id} className="service-checkbox">
                <input
                  checked={values.githubConnectorServices.includes(service.id)}
                  type="checkbox"
                  onChange={() => onConnectorServiceToggle("github", service.id)}
                />
                <span>{serviceIcon(service.id)}</span>
                {service.label}
              </label>
            ))}
          </div>
          <div className="connector-form connector-form-single">
            <Field
              label={copy("githubToken")}
              hint={isExistingSecret(values.githubToken) ? copy("configured") : copy("required")}
              invalid={!!errors.githubToken}
            >
              <Input {...form.register("githubToken")} type="password" />
            </Field>
          </div>
          <ConnectorStatusLine status={githubStatus} fallback={copy("connectorStatusUnavailable")} />
        </section>
      ) : null}

      {connectorMessage ? (
        <div className={cn("connector-action-message reveal-form", `connector-action-${connectorMessageTone}`)}>
          {connectorMessageTone === "success" ? <CheckCircle2 /> : connectorMessageTone === "error" ? <AlertCircle /> : <Info />}
          <span>{connectorMessage}</span>
        </div>
      ) : null}
    </StepSection>
  );
}
