import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

  return (
    <Card className="border-white/6 bg-[var(--surface-panel)] py-0 shadow-[0_24px_80px_rgba(0,0,0,0.28)]">
      <CardContent className="p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="rounded-full bg-white/[0.06] text-[var(--text-strong)]">
            Active filters
          </Badge>
          <span className="text-xs text-[var(--text-dim)]">Scope the dashboard without leaving the working surface.</span>
        </div>

        <div className="grid gap-3 xl:grid-cols-[140px_180px_180px_minmax(260px,1fr)_auto]">
          <label className="grid gap-1.5">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Window</span>
            <Select
              value={String(filters.windowMinutes)}
              onValueChange={(value) =>
                onChange({ ...filters, windowMinutes: Number(value) as DashboardFilters["windowMinutes"] })
              }
            >
              <SelectTrigger className="rounded-2xl border-white/8 bg-[var(--field-bg)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="15">15m</SelectItem>
                <SelectItem value="60">1h</SelectItem>
                <SelectItem value="240">4h</SelectItem>
                <SelectItem value="1440">24h</SelectItem>
              </SelectContent>
            </Select>
          </label>

          <label className="grid gap-1.5">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Service</span>
            <Select
              value={filters.service}
              onValueChange={(value) => onChange({ ...filters, service: value as DashboardFilters["service"] })}
            >
              <SelectTrigger className="rounded-2xl border-white/8 bg-[var(--field-bg)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All services</SelectItem>
                <SelectItem value="gateway">Gateway</SelectItem>
                <SelectItem value="octo">Octo</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="exec_run">Exec run</SelectItem>
                <SelectItem value="mcp">MCP</SelectItem>
                <SelectItem value="workers">Workers</SelectItem>
              </SelectContent>
            </Select>
          </label>

          <label className="grid gap-1.5">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Environment</span>
            <Select
              value={filters.environment}
              onValueChange={(value) =>
                onChange({ ...filters, environment: value as DashboardFilters["environment"] })
              }
            >
              <SelectTrigger className="rounded-2xl border-white/8 bg-[var(--field-bg)]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All environments</SelectItem>
                <SelectItem value="local">Local</SelectItem>
                <SelectItem value="dev">Dev</SelectItem>
                <SelectItem value="staging">Staging</SelectItem>
                <SelectItem value="prod">Prod</SelectItem>
              </SelectContent>
            </Select>
          </label>

          <label className="grid gap-1.5">
            <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--text-dim)]">Dashboard token</span>
            <Input
              value={draftToken}
              onChange={(event) => setDraftToken(event.target.value)}
              type="password"
              placeholder="Optional access token"
              className="rounded-2xl border-white/8 bg-[var(--field-bg)]"
            />
          </label>

          <div className="flex items-end gap-2">
            <Button
              type="button"
              variant="secondary"
              className="rounded-2xl bg-white/[0.08] text-[var(--text-strong)] hover:bg-white/[0.12]"
              onClick={() => onChange({ ...filters, token: draftToken.trim() })}
            >
              Apply
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="rounded-2xl text-[var(--text-muted)] hover:bg-white/[0.05] hover:text-[var(--text-strong)]"
              onClick={() => {
                setDraftToken("");
                onChange({ ...filters, token: "" });
              }}
            >
              Clear
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
