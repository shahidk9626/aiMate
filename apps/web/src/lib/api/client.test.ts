import { describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "@/lib/api/client";
import { mockFetch } from "@/test/fetch-mock";

const BASE = "http://api.test";

async function captureError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to fail");
}

describe("apiGet", () => {
  it("returns data, status and request id on success", async () => {
    const fetchMock = mockFetch({
      "/healthz": { status: 200, body: { status: "ok" }, headers: { "X-Request-ID": "req-123456" } },
    });

    const result = await apiGet<{ status: string }>("/healthz", { baseUrl: BASE });

    expect(result).toEqual({ data: { status: "ok" }, status: 200, requestId: "req-123456" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe(`${BASE}/healthz`);
    expect(init?.credentials).toBe("include");
    expect(init?.method).toBe("GET");
  });

  it("maps the API error envelope to ApiError", async () => {
    mockFetch({
      "/api/v1/leads/1": {
        status: 404,
        body: {
          error: { code: "LEAD_NOT_FOUND", message: "Lead not found.", details: [] },
          meta: { request_id: "req-abcdef12" },
        },
      },
    });

    const error = await captureError(apiGet("/api/v1/leads/1", { baseUrl: BASE }));

    expect(error).toMatchObject({
      status: 404,
      code: "LEAD_NOT_FOUND",
      message: "Lead not found.",
      requestId: "req-abcdef12",
    });
  });

  it("uses HTTP_ERROR for non-envelope error bodies", async () => {
    mockFetch({ "/x": { status: 502, body: "<html>Bad gateway</html>" } });

    const error = await captureError(apiGet("/x", { baseUrl: BASE }));

    expect(error).toMatchObject({ status: 502, code: "HTTP_ERROR" });
  });

  it("treats accepted non-2xx statuses as data", async () => {
    mockFetch({ "/readyz": { status: 503, body: { status: "unavailable" } } });

    const result = await apiGet("/readyz", { baseUrl: BASE, acceptStatuses: [503] });

    expect(result.status).toBe(503);
    expect(result.data).toEqual({ status: "unavailable" });
  });

  it("reports network failures as NETWORK_ERROR", async () => {
    mockFetch({ "/healthz": new TypeError("Failed to fetch") });

    const error = await captureError(apiGet("/healthz", { baseUrl: BASE }));

    expect(error).toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });

  it("reports slow responses as TIMEOUT", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );

    const error = await captureError(apiGet("/slow", { baseUrl: BASE, timeoutMs: 20 }));

    expect(error.code).toBe("TIMEOUT");
  });

  it("rejects success responses that are not JSON", async () => {
    mockFetch({ "/healthz": { status: 200, body: "not json" } });

    const error = await captureError(apiGet("/healthz", { baseUrl: BASE }));

    expect(error.code).toBe("INVALID_RESPONSE");
  });
});
