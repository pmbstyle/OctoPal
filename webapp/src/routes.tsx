import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "./ui/AppShell";
import { RouteErrorBoundary } from "./ui/RouteErrorBoundary";
import { OverviewPage } from "./pages/OverviewPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { QueenPage } from "./pages/QueenPage";
import { WorkersPage } from "./pages/WorkersPage";
import { SystemPage } from "./pages/SystemPage";
import { ActionsPage } from "./pages/ActionsPage";

export const appRouter = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <Navigate to="/overview" replace /> },
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
]);
