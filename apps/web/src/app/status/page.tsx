import type { Metadata } from "next";
import Link from "next/link";

import { SystemStatus } from "@/components/system-status";

export const metadata: Metadata = {
  title: "System status · AI LeadFlow",
};

export default function StatusPage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-12 sm:px-6">
      <div>
        <Link href="/" className="text-sm text-zinc-600 hover:underline dark:text-zinc-400">
          ← AI LeadFlow
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">System status</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Live checks from your browser to the API, database and queue.
        </p>
      </div>
      <SystemStatus />
    </main>
  );
}
