import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";

export type DashboardFilters = {
  windowMinutes: 15 | 60 | 240 | 1440;
  service: "all" | "gateway" | "octo" | "telegram" | "exec_run" | "mcp" | "workers";
  environment: "all" | "local" | "dev" | "staging" | "prod";
  token: string;
};

type GlobalFiltersBarProps = {
  filters: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
};

export function GlobalFiltersBar({ filters, onChange }: GlobalFiltersBarProps) {
  const [draftToken, setDraftToken] = useState<string>(filters.token);

  useEffect(() => {
    setDraftToken(filters.token);
  }, [filters.token]);

  const onSelectWindow = (event: ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...filters, windowMinutes: Number(event.target.value) as DashboardFilters["windowMinutes"] });
  };

  const onTokenChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraftToken(event.target.value);
  };

  return (
    <section
      className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl shadow-slate-950/60"
      aria-label="Global filters"
    >
      <div className="grid gap-3 md:grid-cols-[minmax(220px,320px)_1fr]">
        <label className="grid gap-1 text-xs uppercase tracking-[0.14em] text-slate-400">
          Window
          <select
            value={filters.windowMinutes}
            onChange={onSelectWindow}
            className="rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-cyan-400 focus:outline-none"
          >
          <option value={15}>15m</option>
          <option value={60}>1h</option>
          <option value={240}>4h</option>
          <option value={1440}>24h</option>
          </select>
        </label>

        <label className="grid gap-1 text-xs uppercase tracking-[0.14em] text-slate-400">
          Dashboard token
          <div className="flex gap-2">
            <input
              value={draftToken}
              onChange={onTokenChange}
              type="password"
              placeholder="optional"
              className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 focus:border-cyan-400 focus:outline-none"
            />
            <button
              type="button"
              className="rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-3 py-2 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/25"
              onClick={() => onChange({ ...filters, token: draftToken.trim() })}
            >
              Apply
            </button>
            <button
              type="button"
              className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-700"
              onClick={() => {
                setDraftToken("");
                onChange({ ...filters, token: "" });
              }}
            >
              Clear
            </button>
          </div>
        </label>
      </div>
    </section>
  );
}
