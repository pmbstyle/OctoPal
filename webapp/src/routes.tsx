import { createBrowserRouter, Navigate } from "react-router-dom";

import { ActionsPage } from "./pages/ActionsPage";
import { ControlCenterPage } from "./pages/ControlCenterPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { QueenPage } from "./pages/QueenPage";
import { SystemPage } from "./pages/SystemPage";
import { WorkersPage } from "./pages/WorkersPage";
import { AppShell } from "./ui/AppShell";
import { RouteErrorBoundary } from "./ui/RouteErrorBoundary";

export const appRouter = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      {
        index: true,
        element: <ControlCenterPage />,
      },
      {
        path: "overview",
        element: <OverviewPage />,
      },
      {
        path: "incidents",
        element: <IncidentsPage />,
      },
      {
        path: "queen",
        element: <QueenPage />,
      },
      {
        path: "workers",
        element: <WorkersPage />,
      },
      {
        path: "system",
        element: <SystemPage />,
      },
      {
        path: "actions",
        element: <ActionsPage />,
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
], {
  basename: "/dashboard",
});
