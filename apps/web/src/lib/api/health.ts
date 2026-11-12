/** Health and readiness probes (docs/API_CONTRACTS.md, Stage 1). */

import { apiGet, type RequestOptions } from "@/lib/api/client";

export type CheckStatus = "ok" | "unavailable";

export interface HealthResponse {
  status: "ok";
}

export interface ReadinessResponse {
  status: "ok" | "unavailable";
  checks: {
    database: CheckStatus;
    redis: CheckStatus;
  };
}

export function getHealth(options?: RequestOptions) {
  return apiGet<HealthResponse>("/healthz", options);
}

export function getReadiness(options?: RequestOptions) {
  // 503 is a normal answer here: "not ready", with per-dependency detail.
  return apiGet<ReadinessResponse>("/readyz", { ...options, acceptStatuses: [503] });
}
