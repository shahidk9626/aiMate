"use client";

import { useCallback, useEffect, useState } from "react";

import { checkSystem, type ServiceState, type SystemSnapshot } from "@/lib/system-status";

const REFRESH_MS = 15_000;

const SERVICES: { key: "api" | "database" | "redis"; label: string; description: string }[] = [
  { key: "api", label: "API", description: "FastAPI application server" },
  { key: "database", label: "Database", description: "PostgreSQL" },
  { key: "redis", label: "Queue & cache", description: "Redis" },
];

const STATE_STYLES: Record<ServiceState, { text: string; dot: string; label: string }> = {
  operational: { text: "text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500", label: "Operational" },
  unavailable: { text: "text-red-700 dark:text-red-400", dot: "bg-red-500", label: "Unavailable" },
  unknown: { text: "text-zinc-500 dark:text-zinc-400", dot: "bg-zinc-400", label: "Unknown" },
};

function StateBadge({ state }: { state: ServiceState }) {
  const style = STATE_STYLES[state];
  return (
    <span className={`inline-flex items-center gap-2 text-sm font-medium ${style.text}`}>
      <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}

export function SystemStatus() {
  const [snapshot, setSnapshot] = useState<SystemSnapshot | null>(null);
  // Starts true: the first check begins as soon as the component mounts.
  const [checking, setChecking] = useState(true);
  // Incremented by the button and the timer; each value triggers one check.
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => {
    setChecking(true);
    setRefreshKey((key) => key + 1);
  }, []);

  // One cancellable check per refreshKey. State is only set in the promise
  // callback, and a superseded (aborted) check never overwrites a newer one.
  useEffect(() => {
    const controller = new AbortController();
    checkSystem(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setSnapshot(result);
        setChecking(false);
      })
      .catch(() => {
        // checkSystem reports failures in the snapshot; nothing to do here.
      });
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const allOperational =
    snapshot !== null && SERVICES.every((service) => snapshot[service.key] === "operational");

  return (
    <section aria-labelledby="system-status-heading" className="w-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="system-status-heading" className="text-lg font-semibold">
          Services
        </h2>
        <button
          type="button"
          onClick={refresh}
          disabled={checking}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 disabled:cursor-wait disabled:opacity-60 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          {checking ? "Checking…" : "Check again"}
        </button>
      </div>

      <p aria-live="polite" className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        {snapshot === null
          ? "Checking services…"
          : allOperational
            ? "All services are operational."
            : "Some services are not available."}
      </p>

      <ul className="mt-4 divide-y divide-zinc-200 rounded-lg border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
        {SERVICES.map((service) => (
          <li key={service.key} className="flex items-center justify-between gap-4 px-4 py-3">
            <div>
              <p className="font-medium">{service.label}</p>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">{service.description}</p>
            </div>
            <StateBadge state={snapshot?.[service.key] ?? "unknown"} />
          </li>
        ))}
      </ul>

      {snapshot?.problem ? (
        <div
          role="alert"
          className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
        >
          <p className="font-medium">{snapshot.problem.message}</p>
          <p className="mt-1">
            Code <code>{snapshot.problem.code}</code>
            {snapshot.problem.requestId ? (
              <>
                {" "}
                · Request ID <code>{snapshot.problem.requestId}</code>
              </>
            ) : null}
          </p>
          {snapshot.problem.code === "NETWORK_ERROR" ? (
            <p className="mt-1">
              Is the API running, and is this page opened from the origin set in <code>WEB_ORIGIN</code>?
            </p>
          ) : null}
        </div>
      ) : null}

      {snapshot ? (
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          Last checked {snapshot.checkedAt.toLocaleTimeString()} · refreshes every {REFRESH_MS / 1000}s
        </p>
      ) : null}
    </section>
  );
}
