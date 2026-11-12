import { vi } from "vitest";

type Route = { status: number; body?: unknown; headers?: Record<string, string> } | Error;

/**
 * Stubs global fetch with fixed responses per path suffix
 * (e.g. "/healthz"). An Error value simulates a network failure.
 */
export function mockFetch(routes: Record<string, Route>) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- keeps fetch's signature for call assertions
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    const match = Object.entries(routes).find(([suffix]) => url.endsWith(suffix));
    if (!match) throw new Error(`Unexpected fetch: ${url}`);
    const route = match[1];
    if (route instanceof Error) throw route;
    const body = route.body === undefined ? "" : typeof route.body === "string" ? route.body : JSON.stringify(route.body);
    return new Response(body, {
      status: route.status,
      headers: { "Content-Type": "application/json", ...route.headers },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
