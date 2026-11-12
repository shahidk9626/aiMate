# Development Progress

## Current state

**Milestone:** Stage 2 — Authentication and multi-tenancy — step 2.1 of 7 complete
**Branch:** `stage-2/auth-tenancy` (based on `stage-1/foundation`; neither merged into `main` yet).
**Design:** `docs/STAGE_2_DESIGN.md`, approved 2026-11-12 (ADR-023).
**Stage 1:** COMPLETE (2026-11-12).

## Completed

### Day 1 — Architecture review (2026-11-12)
- Read HLD v1.0 and LLD v1.0; wrote the review (15 inconsistencies, 12 missing requirements) and ADR-003 … ADR-016.
- Proposed schema v1.1 and the API surface; looked up current dependency versions.
- Product owner approved all corrections, ADRs and decisions D1–D10 on 2026-11-12.
- Docs committed to `main` (commit `dff7016`).

### Stage 1, step 1 — Repository skeleton and local data services (2026-11-12)

Files created:
- `.gitignore` — ignores `.env*` (except `.env.example`), Python/Node build output, caches.
- `.env.example` — PostgreSQL and Redis variables with `change-me` placeholders.
- `infra/docker-compose.yml` — PostgreSQL 17 + Redis 8, health checks, named volumes, localhost-only ports, Redis password required, missing-variable guard.
- `README.md` — overview, layout, quick start, documentation index.

Docs updated: `ARCHITECTURE_DECISIONS.md` (all ADRs Accepted, ADR-017 added), `KNOWN_ISSUES.md`, `SETUP_GUIDE.md`, this file.

Directory decision: `apps/api`, `apps/web`, `apps/widget`, `packages/contracts` are **not** created as empty placeholders; each appears in the step that builds it (`create-next-app` also refuses non-empty target directories).

Verification (manual, all passed):
| Check | Result |
|---|---|
| `docker compose config` with `.env` | Valid |
| `.env` git-ignored | Yes |
| Both services healthy after `up -d` | Healthy in ~6 s |
| PostgreSQL version / timezone / encoding | 17.11 / UTC / UTF8 |
| Host TCP login with correct password | OK |
| Login with wrong password | Rejected |
| `citext`, `pgcrypto` extensions available | Yes (1.6, 1.3) |
| Redis with password | `PONG` |
| Redis without password | `NOAUTH Authentication required` |
| Redis password absent from container args | Yes |
| Data survives `docker compose restart` | Yes |
| Ports bound to 127.0.0.1 only | Yes |

Automated tests: none yet (no application code). The first pytest suite arrives in step 2.

### Stage 1, step 2 — FastAPI application skeleton (2026-11-12)

Files created in `apps/api/`:
- `pyproject.toml`, `uv.lock` — Python 3.13, uv-managed; ruff (incl. bandit rules), strict mypy, pytest with warnings-as-errors.
- `README.md` — commands and layout.
- `app/main.py` — `create_app(settings)` factory.
- `app/core/config.py` — typed, immutable settings (`APP_ENV`, `LOG_LEVEL`, `LOG_JSON`).
- `app/core/logging.py` — structlog; JSON outside local; uvicorn logs routed through it; secret-key redaction.
- `app/core/request_context.py` — pure-ASGI `X-Request-ID` middleware + access log without query strings.
- `app/core/errors.py` — `AppError` hierarchy (`NotFound`, `Conflict`, `PermissionDenied`, `Authentication`) and envelope handlers for app, validation, HTTP and unhandled errors.
- `app/api/health.py` — `GET /healthz`; `app/api/v1/router.py` — empty `/api/v1` router.
- `tests/` — `conftest.py`, `test_health.py`, `test_request_id.py`, `test_errors.py`, `test_config.py`, `test_logging.py`.

Docs updated: `API_CONTRACTS.md` (envelope + health implemented), `ARCHITECTURE_DECISIONS.md` (ADR-018, ADR-019), `SETUP_GUIDE.md`, this file.

Issue found and fixed: Starlette 1.10 deprecates `httpx` for its TestClient; switched the dev dependency to `httpx2` (ADR-019).

Results:
| Check | Result |
|---|---|
| `pytest` | **27 passed** (0.2 s) |
| `ruff check` / `ruff format --check` | Clean |
| `mypy` (strict, app + tests) | No issues in 18 files |
| Manual uvicorn run (`APP_ENV=staging`) | `/healthz` 200 with `X-Request-ID`; 404 in envelope; all logs JSON; query string absent from access log |

What the tests cover: liveness; request-id generation, propagation and rejection of unsafe values; request id on 404/500; envelope for app errors, validation (no input echo), 404, 405, 500 (no internals leaked); settings defaults/env/invalid values/immutability; docs hidden in production; access log without query string; redaction; unhandled exceptions logged with request id.

### Stage 1, step 3 — Database layer (2026-11-12)

Dependencies added (runtime): `sqlalchemy[asyncio]` 2.1.8, `psycopg[binary]` 3.3.9, `alembic` 1.20.1, `redis` 8.1.0. `pytest-asyncio` was **not** added: anyio's pytest plugin (already present) runs async tests.

Files created in `apps/api/`:
- `app/db/base.py` (Base, naming conventions, UUID PK + timestamp mixins), `ids.py` (UUIDv7), `engine.py` (async + sync engines), `session.py` (`DbSession` dependency), `tenant.py` (`set_tenant` / `set_tenant_sync`), `rls.py` (policy SQL), `models.py` (registry), `bootstrap.py` (runtime role command).
- `app/core/redis.py` — async Redis client factory.
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_baseline.py`.
- Tests: `test_ids.py`, `test_rls_sql.py`, `test_db_config.py`, `test_readyz.py`, `tests/integration/{conftest,test_migrations,test_app_role,test_tenant_isolation,test_app_live}.py`.

Files modified: `app/core/config.py` (database/Redis settings, secrets required in staging/production), `app/api/health.py` (`/readyz`), `app/main.py` (engine/Redis lifecycle), `pyproject.toml`, `uv.lock`, `tests/test_config.py` (supply secrets for production settings), `.env.example`, `apps/api/README.md`.

Docs updated: `ARCHITECTURE_DECISIONS.md` (ADR-020), `DATABASE_SCHEMA.md` (revision 0001, roles, conventions, RLS verified), `API_CONTRACTS.md` (`/readyz`), `SETUP_GUIDE.md` (bootstrap, migrations, test commands, consolidated env vars), `KNOWN_ISSUES.md`, this file.

Results:
| Check | Result |
|---|---|
| `pytest` (all) | **74 passed** (3.4 s): 54 unit + 20 integration |
| Integration tests with PostgreSQL stopped | Skipped with reason, not failed |
| Test database/role cleaned up after run | Yes |
| `ruff check`, `ruff format --check`, strict `mypy` | Clean (38 files) |
| `python -m app.db.bootstrap` on dev DB | Created role; second run updated (idempotent) |
| `alembic upgrade head` on dev DB | At `0001 (head)` |
| `/readyz` live, Redis stopped, Redis restarted | 200 → 503 (`redis: unavailable`) → 200 |

What the integration tests prove: app role is not superuser/BYPASSRLS, cannot create tables or read `alembic_version`; app connects as that role; migrations go base → head → base → head; models and migrations are in sync; with the shipped RLS policy a tenant sees only its rows, no tenant context sees and inserts nothing, rows cannot be inserted for, moved to, or modified in another tenant, and tenant context does not survive a commit on the same pooled connection (sync and async).

### Stage 1, step 4 — Web app foundation (2026-11-12)

Scaffolded with `create-next-app@16.4.6`; every generated file was read before changes. Bundled Next.js 16 docs consulted for Cache Components, Partial Prefetching, environment variables, TypeScript typegen and Vitest.

Files created / changed:
- Repo root: `package.json` (workspace scripts, pnpm 10.28 pinned, Node ≥ 22.12), `pnpm-workspace.yaml`, `pnpm-lock.yaml`; `.env.example` (+ `WEB_ORIGIN`); `README.md` (quick start for the whole stack).
- `apps/web/` (`@leadflow/web`): scaffold config (`next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `AGENTS.md`, `.gitignore` + `!.env.example`), `.env.example`, `README.md`, `vitest.config.mts`, `vitest.setup.ts`.
- `src/app/layout.tsx` (title, `noindex`, font fix), `globals.css`, `page.tsx` (honest preview landing), `status/page.tsx`.
- `src/components/system-status.tsx`; `src/lib/config.ts`, `src/lib/api/client.ts`, `src/lib/api/health.ts`, `src/lib/system-status.ts`; `src/test/fetch-mock.ts`.
- Tests: `config.test.ts`, `api/client.test.ts`, `system-status.test.tsx`, `app/page.test.tsx`.
- Scaffold demo images in `public/` removed.
- API: `app/core/config.py` (`WEB_ORIGIN` with validation), `app/main.py` (CORS middleware), `tests/test_cors.py` (new), `tests/test_config.py` and `tests/test_db_config.py` (supply an https origin for production settings).

Docs updated: `ARCHITECTURE_DECISIONS.md` (ADR-021), `API_CONTRACTS.md` (CORS), `SETUP_GUIDE.md` (web setup, versions, env vars), `KNOWN_ISSUES.md`, this file.

Problems found and resolved:
- React lint rule `set-state-in-effect` flagged the first polling implementation; rewritten to the recommended pattern.
- ESLint 10 tried: its plugins in `eslint-config-next` do not support it yet; stayed on 9.
- Scaffold CSS forced Arial over the loaded Geist font; fixed.

Results:
| Check | Result |
|---|---|
| Web `pnpm check` (ESLint, `next typegen` + `tsc`, Vitest) | Clean; **16 tests passed** |
| `next build` with `NEXT_PUBLIC_API_URL` | Success; `/`, `/status` prerendered |
| `next build` without it | Fails with a clear message (intended) |
| API `pytest` | **91 passed** (71 unit + 20 integration), ruff + strict mypy clean |
| Real browser (Chromium via Playwright), `next start` + API | All three services "Operational"; with Redis stopped only "Queue & cache" shows "Unavailable"; from untrusted origin `127.0.0.1:3000` the browser blocks the request (CORS) and the page explains it |

### Stage 1, step 5 — Containers, one-command stack, HLD/LLD v1.1 (2026-11-12)

Files created: `apps/api/Dockerfile`, `apps/api/.dockerignore`, `apps/web/Dockerfile`, `apps/web/Dockerfile.dockerignore`.
Files changed:
- `infra/docker-compose.yml`: profile `app` with `migrate`, `api`, `web`.
- `.env.example`: `API_PORT`, `WEB_PORT`.
- `apps/web/next.config.ts`: standalone output, tracing root, `poweredByHeader: false`.
- `apps/api/app/core/config.py`: env-file lookup fixed for the container layout. This was a crash bug found during the step; `/app` has no repo root.
- `apps/api/app/core/request_context.py`: successful health probes not logged.
- `apps/api/app/main.py`: trusted origin logged at startup.
- `apps/api/tests/test_logging.py`: 3 new tests, privacy test moved to a logged path.
- `docs/AI-LeadFlow-HLD.html`, `docs/AI-LeadFlow-LLD.html`: revised to **v1.1**.
- `README.md`, all docs.

Bug caught in review before commit: the first version of the quiet-probe change used `return` inside `finally`, which would have swallowed exceptions; rewritten as a conditional.

Results:
| Check | Result |
|---|---|
| API `pytest` | **94 passed** (74 unit + 20 integration); ruff + strict mypy clean |
| Web `pnpm check` | Clean; 16 tests passed; standalone build OK |
| API image | Builds; runs as uid 10001; code read-only; no dev tools, `.env` or CA in layers; 306 MB |
| Web image | Builds; runs as `node`; no proxy/CA in layers; API URL baked in; 413 MB |
| `compose --profile app up` from **empty volumes** | All healthy in ~15 s: migrate bootstrapped role + ran `0001`, api ready, web healthy |
| Second `up` | migrate re-runs safely (role "updated", no migrations pending) |
| Browser against containers | Status page all "Operational"; no `X-Powered-By`; API DB sessions use `leadflow_app` |
| Owner credentials | Only in `migrate` and `postgres` service environments |
| HLD/LLD v1.1 | Render without errors |

## Stage 1 sign-off

What exists:
- **Monorepo:** `apps/api` (uv), `apps/web` (pnpm workspace), `infra`, `docs`.
- **API:** FastAPI with typed settings, JSON logs without PII, request ids, error envelope, CORS for one origin, `/healthz` and `/readyz`.
- **Database:** PostgreSQL 17 with a restricted runtime role, Alembic baseline, and an RLS mechanism proven by tests.
- **Web:** Next.js 16 app with a typed API client and a live status page.
- **Docker:** images for API and web; the whole stack starts with one command.
- **Tests:** 94 API and 16 web, plus browser checks.
- **Docs:** up to date, including HLD/LLD v1.1.

Not built in Stage 1, by design: authentication, tenants, any product feature, the Celery worker, CI.

### Stage 2, step 2.1 — Identity and tenancy data model with RLS (2026-11-12)

Files created:
- `app/modules/{identity,tenancy,audit,outbox}/models.py`
- `alembic/versions/0002_identity_and_tenancy.py`
- `tests/integration/test_identity_tenancy_rls.py` (27 tests)

Files changed:
- `app/db/base.py`: `TenantMixin`, `tenant_table_args`, `str_enum`.
- `app/db/tenant.py`: `set_current_user` alongside `set_tenant`.
- `app/db/rls.py`: `CURRENT_TENANT` / `CURRENT_USER`, `force_rls_sql`.
- `app/db/models.py`: registry.
- `app/core/config.py`: `db_lookup_role`; role names limited to 56 characters.
- `tests/integration/conftest.py`: drops the lookup role.
- `tests/integration/test_migrations.py`: head no longer hard-coded.

Design refinement found while implementing:
- Under FORCE RLS a non-superuser owner cannot see rows, so the lookup functions are owned by a dedicated NOLOGIN lookup role with column-level grants.
- RLS was extended to `users`, `auth_sessions` and `email_tokens`.

Both are recorded in ADR-023.

Bug caught by the tests and fixed: the downgrade failed because the `tenants` and `users` policies depend on `memberships`; they are now dropped first.

Results:
| Check | Result |
|---|---|
| `pytest` | **121 passed**: 47 integration (27 new) + 74 unit |
| ruff, strict mypy | Clean (49 files) |
| Dev DB `0002 → 0001 → 0002` | OK; `alembic check`: no drift |
| DB inspection | RLS forced on every table except `outbox_events`; check constraints named; functions owned by `leadflow_app_lookup`, executable only by the app role |

What the new tests prove:
- With no identity set, nothing is visible.
- A user sees only their own user row and their own businesses; Carol sees both of hers.
- In a business, you see teammates but not another business's users. A disabled membership hides the business.
- Nobody can create or modify another user's row, add a membership to another business, change or delete another business's members, delete businesses or users, or create sessions for others.
- Sessions and tokens are private to their user.
- The audit log is scoped per business and append-only.
- Invitations are isolated, with one open invitation per email per business.
- The lookup functions return ids only and ignore revoked, expired, used or wrong-purpose tokens.
- The lookup role can't log in, read password hashes or other tables, or create objects; the app role can't become it; PUBLIC can't call the functions.
- The database itself rejects invalid roles.

## Exact next task

**Stage 2, step 2.2 — security plumbing** (no endpoints yet):
1. Add `argon2-cffi`: password hashing with rehash-on-login and a dummy verify for unknown emails.
2. Session token helpers: generate, hash, cookie name and attributes per environment.
3. Redis rate limiter (fixed window, in-house).
4. CSRF middleware: `X-Requested-With` + `Origin` on unsafe methods.
5. Security headers middleware; 1 MB request body limit; catch-all error middleware inside CORS (the 500-with-CORS fix).
6. Unit and integration tests; docs; stop and report.

Original Stage 2 brief (now covered by the design document):
1. Data model for migration `0002`: `users`, `tenants`, `memberships`, `auth_sessions`, `password_reset_tokens`, `invitations`, `audit_logs`. RLS on tenant tables. Tenant mixin (`tenant_id`, `UNIQUE(tenant_id, id)`).
2. Endpoint contracts: register, login, refresh, logout, me, password forgot/reset, tenant profile, members, invitations.
3. New dependencies to explain: `argon2-cffi` (passwords), `pyjwt` (access tokens).
4. Security controls landing with auth: CSRF check, login/reset rate limiting, security headers, request size limit, the 500-with-CORS fix.
5. Decision needed from the product owner: **transactional email provider** (password reset, invitations), from Postmark, Resend or Amazon SES. Local development uses a mail-catcher container.
6. Web: sign-up, login and workspace selection pages.

Suggested before Stage 2:
- Merge `stage-1/foundation` into `main` via a pull request.
- Add a CI workflow (GitHub Actions) that runs the API and web checks on every push.

## Stage tracker

| Stage | Scope | Status |
|---|---|---|
| 0 | Architecture review | Done, approved |
| 1 | Foundation | **Done** (2026-11-12) |
| 2 | Auth + multi-tenancy | In progress — step 2.1 of 7 done |
| 3 | CRM | Not started |
| 4 | Unified inbox | Not started |
| 5 | Website widget | Not started |
| 6 | AI engine | Not started |
| 7 | Instagram + Facebook | Not started |
| 8 | Automation + analytics | Not started |
| 9 | Commercial launch | Not started |
