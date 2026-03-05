import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";

export type DashboardFilters = {
  windowMinutes: 15 | 60 | 240 | 1440;
  service: "all" | "gateway" | "queen" | "telegram" | "exec_run" | "mcp" | "workers";
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

  const onSelectService = (event: ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...filters, service: event.target.value as DashboardFilters["service"] });
  };

  const onSelectEnvironment = (event: ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...filters, environment: event.target.value as DashboardFilters["environment"] });
  };

  const onTokenChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraftToken(event.target.value);
  };

  return (
    <section className="filters" aria-label="Global filters">
      <label>
        Window
        <select value={filters.windowMinutes} onChange={onSelectWindow}>
          <option value={15}>15m</option>
          <option value={60}>1h</option>
          <option value={240}>4h</option>
          <option value={1440}>24h</option>
        </select>
      </label>

      <label>
        Service
        <select value={filters.service} onChange={onSelectService}>
          <option value="all">All services</option>
          <option value="gateway">Gateway</option>
          <option value="queen">Queen</option>
          <option value="telegram">Telegram</option>
          <option value="exec_run">Exec Run</option>
          <option value="mcp">MCP</option>
          <option value="workers">Workers</option>
        </select>
      </label>

      <label>
        Environment
        <select value={filters.environment} onChange={onSelectEnvironment}>
          <option value="all">All</option>
          <option value="local">local</option>
          <option value="dev">dev</option>
          <option value="staging">staging</option>
          <option value="prod">prod</option>
        </select>
      </label>

      <label className="token-field">
        Dashboard token
        <div className="token-controls">
          <input
            value={draftToken}
            onChange={onTokenChange}
            type="password"
            placeholder="optional"
          />
          <button
            type="button"
            className="drill-btn"
            onClick={() => onChange({ ...filters, token: draftToken.trim() })}
          >
            Apply
          </button>
          <button
            type="button"
            className="drill-btn"
            onClick={() => {
              setDraftToken("");
              onChange({ ...filters, token: "" });
            }}
          >
            Clear
          </button>
        </div>
      </label>
    </section>
  );
}
