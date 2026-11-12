import { describe, expect, it } from "vitest";

import { resolveApiBaseUrl } from "@/lib/config";

describe("resolveApiBaseUrl", () => {
  it("defaults to the local API outside production", () => {
    expect(resolveApiBaseUrl(undefined, "development")).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("  ", "test")).toBe("http://localhost:8000");
  });

  it("requires a value for production builds", () => {
    expect(() => resolveApiBaseUrl(undefined, "production")).toThrow(/must be set/);
  });

  it("strips trailing slashes", () => {
    expect(resolveApiBaseUrl("https://api.example.com/", "production")).toBe("https://api.example.com");
  });

  it("rejects invalid URLs and non-http schemes", () => {
    expect(() => resolveApiBaseUrl("not a url", "development")).toThrow(/not a valid URL/);
    expect(() => resolveApiBaseUrl("javascript:alert(1)", "development")).toThrow(/http or https/);
  });
});
