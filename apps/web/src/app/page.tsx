import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-4 py-16 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-teal-700 dark:text-teal-400">
        Development preview
      </p>
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">AI LeadFlow</h1>
      <p className="text-lg text-zinc-700 dark:text-zinc-300">
        Never miss a customer enquiry again. Let AI respond, qualify, organize and route your leads
        automatically.
      </p>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        This build contains the platform foundation only. Sign-in, the CRM and the unified inbox
        arrive in the next stages.
      </p>
      <div>
        <Link
          href="/status"
          className="inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          View system status
        </Link>
      </div>
    </main>
  );
}
