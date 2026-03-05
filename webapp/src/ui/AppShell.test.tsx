import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { appRouter } from "../routes";

describe("AppShell", () => {
  it("renders navigation tabs", () => {
    const router = createMemoryRouter(appRouter.routes, {
      initialEntries: ["/workers"],
    });

    render(<RouterProvider router={router} />);

    expect(screen.getByText("Control Deck")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Incidents" })).toBeInTheDocument();
    expect(screen.getByText("Window")).toBeInTheDocument();
    expect(screen.getByText("Service")).toBeInTheDocument();
  });
});
