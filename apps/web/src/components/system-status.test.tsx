import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SystemStatus } from "@/components/system-status";
import { mockFetch } from "@/test/fetch-mock";

function row(label: string) {
  return within(screen.getByText(label, { selector: "p" }).closest("li")!);
}

describe("SystemStatus", () => {
  it("shows every service operational when the API is ready", async () => {
    mockFetch({
      "/healthz": { status: 200, body: { status: "ok" } },
      "/readyz": { status: 200, body: { status: "ok", checks: { database: "ok", redis: "ok" } } },
    });

    render(<SystemStatus />);

    expect(await screen.findByText("All services are operational.")).toBeInTheDocument();
    for (const label of ["API", "Database", "Queue & cache"]) {
      expect(row(label).getByText("Operational")).toBeInTheDocument();
    }
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("marks only the failing dependency unavailable when readiness is 503", async () => {
    mockFetch({
      "/healthz": { status: 200, body: { status: "ok" } },
      "/readyz": {
        status: 503,
        body: { status: "unavailable", checks: { database: "ok", redis: "unavailable" } },
      },
    });

    render(<SystemStatus />);

    expect(await screen.findByText("Some services are not available.")).toBeInTheDocument();
    expect(row("API").getByText("Operational")).toBeInTheDocument();
    expect(row("Database").getByText("Operational")).toBeInTheDocument();
    expect(row("Queue & cache").getByText("Unavailable")).toBeInTheDocument();
  });

  it("explains when the API cannot be reached", async () => {
    mockFetch({
      "/healthz": new TypeError("Failed to fetch"),
      "/readyz": new TypeError("Failed to fetch"),
    });

    render(<SystemStatus />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not reach the server.");
    expect(alert).toHaveTextContent("NETWORK_ERROR");
    expect(row("API").getByText("Unavailable")).toBeInTheDocument();
    expect(row("Database").getByText("Unknown")).toBeInTheDocument();
  });
});
