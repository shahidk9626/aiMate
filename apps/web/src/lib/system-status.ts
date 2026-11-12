/** Combines the API's liveness and readiness probes into one snapshot. */

import { ApiError } from "@/lib/api/client";
import { getHealth, getReadiness, type CheckStatus } from "@/lib/api/health";

export type ServiceState = "operational" | "unavailable" | "unknown";

export interface SystemSnapshot {
  api: ServiceState;
  database: ServiceState;
  redis: ServiceState;
  checkedAt: Date;
  /** First API failure, if any, for display and support (request id). */
  problem: { code: string; message: string; requestId: string | null } | null;
}

const toState = (status: CheckStatus): ServiceState =>
  status === "ok" ? "operational" : "unavailable";

function describe(reason: unknown): SystemSnapshot["problem"] {
  if (reason instanceof ApiError) {
    return { code: reason.code, message: reason.message, requestId: reason.requestId };
  }
  return { code: "UNKNOWN", message: "Unexpected error while checking the system.", requestId: null };
}

export async function checkSystem(signal?: AbortSignal): Promise<SystemSnapshot> {
  const [health, readiness] = await Promise.allSettled([
    getHealth({ signal }),
    getReadiness({ signal }),
  ]);

  const snapshot: SystemSnapshot = {
    api: health.status === "fulfilled" ? "operational" : "unavailable",
    database: "unknown",
    redis: "unknown",
    checkedAt: new Date(),
    problem: null,
  };

  if (readiness.status === "fulfilled") {
    snapshot.database = toState(readiness.value.data.checks.database);
    snapshot.redis = toState(readiness.value.data.checks.redis);
  }

  const failure =
    health.status === "rejected" ? health.reason : readiness.status === "rejected" ? readiness.reason : null;
  if (failure !== null) snapshot.problem = describe(failure);

  return snapshot;
}
