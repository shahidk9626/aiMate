/**
 * Minimal typed client for the AI LeadFlow API.
 *
 * - Sends cookies (`credentials: "include"`): the dashboard will authenticate
 *   with HttpOnly cookies (ADR-004). Tokens are never stored in JS.
 * - Turns every failure into an `ApiError` with a stable `code`, so UI code
 *   never parses raw responses. Server errors use the API's envelope
 *   (docs/API_CONTRACTS.md); network failures and timeouts get local codes.
 */

import { API_BASE_URL } from "@/lib/config";

export const REQUEST_ID_HEADER = "X-Request-ID";

export type ApiErrorCode =
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "HTTP_ERROR"
  | "INVALID_RESPONSE"
  | (string & {}); // plus any server error code, e.g. "LEAD_NOT_FOUND"

export interface ApiErrorDetail {
  field?: string;
  message: string;
  type?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly requestId: string | null;
  readonly details: ApiErrorDetail[];

  constructor(init: {
    status: number;
    code: ApiErrorCode;
    message: string;
    requestId?: string | null;
    details?: ApiErrorDetail[];
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.details = init.details ?? [];
  }
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  requestId: string | null;
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Abort after this many milliseconds. Default 8000. */
  timeoutMs?: number;
  /** Non-2xx statuses whose body is valid data, e.g. 503 from /readyz. */
  acceptStatuses?: readonly number[];
  /** Override for tests. */
  baseUrl?: string;
}

interface ErrorEnvelope {
  error: { code: string; message: string; details?: ApiErrorDetail[] };
  meta?: { request_id?: string | null };
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = (body as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return undefined; // distinguishes "not JSON" from "empty body"
  }
}

export async function apiGet<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const { timeoutMs = 8000, acceptStatuses = [], baseUrl = API_BASE_URL } = options;
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const signal = options.signal ? AbortSignal.any([options.signal, timeoutSignal]) : timeoutSignal;

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (cause) {
    if (timeoutSignal.aborted) {
      throw new ApiError({ status: 0, code: "TIMEOUT", message: "The server took too long to respond." });
    }
    if (options.signal?.aborted) throw cause; // caller cancelled: not an API failure
    throw new ApiError({ status: 0, code: "NETWORK_ERROR", message: "Could not reach the server." });
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER);
  const body = await readJson(response);

  if (response.ok || acceptStatuses.includes(response.status)) {
    if (body === undefined) {
      throw new ApiError({
        status: response.status,
        code: "INVALID_RESPONSE",
        message: "The server returned an unexpected response.",
        requestId,
      });
    }
    return { data: body as T, status: response.status, requestId };
  }

  if (isErrorEnvelope(body)) {
    throw new ApiError({
      status: response.status,
      code: body.error.code,
      message: body.error.message,
      requestId: body.meta?.request_id ?? requestId,
      details: body.error.details ?? [],
    });
  }
  throw new ApiError({
    status: response.status,
    code: "HTTP_ERROR",
    message: `Request failed with status ${response.status}.`,
    requestId,
  });
}
