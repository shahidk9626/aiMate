import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("names the product and links to the status page", () => {
    render(<HomePage />);

    expect(screen.getByRole("heading", { level: 1, name: "AI LeadFlow" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View system status" })).toHaveAttribute("href", "/status");
  });

  it("does not claim features that are not built yet", () => {
    render(<HomePage />);

    expect(screen.getByText(/foundation only/i)).toBeInTheDocument();
  });
});
