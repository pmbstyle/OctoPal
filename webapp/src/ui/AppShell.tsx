import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { GlobalFiltersBar } from "./GlobalFiltersBar";
import type { DashboardFilters } from "./GlobalFiltersBar";

const navItems = [
  { to: "/overview", label: "Overview" },
  { to: "/incidents", label: "Incidents" },
  { to: "/queen", label: "Queen" },
  { to: "/workers", label: "Workers" },
  { to: "/system", label: "System" },
  { to: "/actions", label: "Actions" },
];

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

  const outletContext = useMemo(
    () => ({ filters, setFilters } satisfies AppShellOutletContext),
    [filters],
  );

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="kicker">BroodMind</p>
          <h1 className="title">Control Deck</h1>
        </div>
        <div className="status-badge">Foundation stage</div>
      </header>

      <nav className="tabs" aria-label="Dashboard sections">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `tab ${isActive ? "tab-active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <GlobalFiltersBar filters={filters} onChange={setFilters} />

      <main className="content">
        <Outlet context={outletContext} />
      </main>
    </div>
  );
}
