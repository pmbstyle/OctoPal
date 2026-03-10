import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { GlobalFiltersBar } from "./GlobalFiltersBar";
import type { DashboardFilters } from "./GlobalFiltersBar";

const filtersStorageKey = "broodmind.webapp.filters";
const tokenStorageKey = "broodmind.webapp.token";

const defaultFilters: DashboardFilters = {
  windowMinutes: 60,
  service: "all",
  environment: "all",
  token: "",
};

export type AppShellOutletContext = {
  filters: DashboardFilters;
  setFilters: (next: DashboardFilters) => void;
};

const navItems = [
  { to: "/", label: "Control" },
  { to: "/overview", label: "Overview" },
  { to: "/workers", label: "Workers" },
  { to: "/queen", label: "Queen" },
  { to: "/incidents", label: "Incidents" },
  { to: "/system", label: "System" },
  { to: "/actions", label: "Actions" },
];

export function AppShell() {
  const [filters, setFilters] = useState<DashboardFilters>(() => {
    const raw = localStorage.getItem(filtersStorageKey);
    const token = sessionStorage.getItem(tokenStorageKey) ?? "";
    if (!raw) {
      return { ...defaultFilters, token };
    }
    try {
      const parsed = JSON.parse(raw) as Partial<DashboardFilters>;
      return {
        windowMinutes:
          parsed.windowMinutes === 15 ||
          parsed.windowMinutes === 60 ||
          parsed.windowMinutes === 240 ||
          parsed.windowMinutes === 1440
            ? parsed.windowMinutes
            : 60,
        service: parsed.service ?? "all",
        environment: parsed.environment ?? "all",
        token,
      };
    } catch (_error) {
      return { ...defaultFilters, token };
    }
  });

  useEffect(() => {
    localStorage.setItem(
      filtersStorageKey,
      JSON.stringify({
        windowMinutes: filters.windowMinutes,
        service: filters.service,
        environment: filters.environment,
      }),
    );
    if (filters.token) {
      sessionStorage.setItem(tokenStorageKey, filters.token);
    } else {
      sessionStorage.removeItem(tokenStorageKey);
    }
  }, [filters]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8 md:py-10">
        <header className="mb-6">
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-300/80">BroodMind</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50 md:text-4xl">
            Operations Control Center
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">
            Live view for queen activity, worker pool, queue pressure and system health.
          </p>
        </header>
        <GlobalFiltersBar filters={filters} onChange={setFilters} />
        <nav className="mt-4 flex flex-wrap gap-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                [
                  "rounded-full border px-3 py-1.5 text-xs uppercase tracking-[0.18em] transition",
                  isActive
                    ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-200"
                    : "border-slate-800 bg-slate-900/70 text-slate-400 hover:border-slate-700 hover:text-slate-200",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <main className="mt-5">
          <Outlet context={{ filters, setFilters }} />
        </main>
        <footer className="mt-8 border-t border-slate-800 pt-4 text-xs text-slate-500">
          Updates every 4 seconds. Streamlined for operator-first monitoring.
        </footer>
      </div>
    </div>
  );
}
