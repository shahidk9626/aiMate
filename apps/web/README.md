# AI LeadFlow Web

Next.js dashboard for AI LeadFlow. Next.js 16 (App Router, Turbopack, Cache Components), React 19, TypeScript 5, Tailwind CSS 4. Part of the pnpm workspace at the repository root.

> Next.js 16 differs from older versions. Before changing framework-level code, read the bundled docs in `node_modules/next/dist/docs/` (see `AGENTS.md`).

## Commands (run from `apps/web`)

| Task | Command |
|---|---|
| Install (from repo root) | `pnpm install` |
| Dev server | `pnpm dev` → http://localhost:3000 |
| Production build | `pnpm build` (needs `NEXT_PUBLIC_API_URL`) |
| Run production build | `pnpm start` |
| Lint | `pnpm lint` |
| Type check | `pnpm typecheck` |
| Unit tests | `pnpm test` (`pnpm test:watch` to watch) |
| All checks | `pnpm check` |

Open the app at **http://localhost:3000**, not `127.0.0.1:3000`: the API only accepts browser requests from the origin in its `WEB_ORIGIN` setting (default `http://localhost:3000`).

## Configuration

Copy `.env.example` to `.env.local`. `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000` in development and is required for production builds. `NEXT_PUBLIC_*` values are inlined at build time and visible to anyone: never put secrets in them.

## Layout

```
src/
├── app/                  # routes (App Router)
│   ├── layout.tsx
│   ├── page.tsx          # /        development preview landing
│   └── status/page.tsx   # /status  live system status
├── components/
│   └── system-status.tsx # client component: polls /healthz and /readyz
├── lib/
│   ├── config.ts         # NEXT_PUBLIC_API_URL validation
│   ├── system-status.ts  # combines probes into one snapshot
│   └── api/
│       ├── client.ts     # typed fetch wrapper, ApiError, cookies included
│       └── health.ts     # probe endpoints
└── test/fetch-mock.ts    # fetch stub for unit tests
```

Tests live next to the code as `*.test.ts(x)` and run in jsdom with Vitest and Testing Library.
