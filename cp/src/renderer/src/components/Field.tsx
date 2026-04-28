import { type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

import { cn } from "../lib/cn";

export function Field({
  label,
  hint,
  children,
  invalid,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  invalid?: boolean;
}) {
  return (
    <label className={cn("field", invalid && "field-invalid")}>
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="input select-input" {...props} />;
}
