# Development Progress

## Current state

**Milestone:** Stage 1 — Foundation
**Status:** Steps 1–3 of 5 complete. Branch `stage-1/foundation`.
**Next:** Stage 1, step 4 — Next.js web app scaffold (see below).

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

## Exact next task

**Stage 1, step 4 — Next.js web app scaffold** in `apps/web`:
1. Verify current Next.js / React / Tailwind / TypeScript compatibility; scaffold with `create-next-app` (App Router, TypeScript, Tailwind, ESLint, `src/` dir) using pnpm; Node 22.
2. Root `package.json` + `pnpm-workspace.yaml` for `apps/web` (and later `apps/widget`, `packages/contracts`).
3. Typed API client module reading `NEXT_PUBLIC_API_URL`; a status page that shows `/healthz` and `/readyz` results.
4. API CORS for the web origin (`WEB_ORIGIN`), restricted to that origin only.
5. Frontend test setup (Vitest + Testing Library) with a first test; lint, type-check, build.
6. Update docs; stop and report.

Remaining Stage 1 steps:
- Step 5: API/web Dockerfiles, full `docker compose up`, HLD/LLD v1.1, Stage 1 sign-off.

## Stage tracker

| Stage | Scope | Status |
|---|---|---|
| 0 | Architecture review | Done, approved |
| 1 | Foundation | In progress — steps 1–3 of 5 done |
| 2 | Auth + multi-tenancy | Not started |
| 3 | CRM | Not started |
| 4 | Unified inbox | Not started |
| 5 | Website widget | Not started |
| 6 | AI engine | Not started |
| 7 | Instagram + Facebook | Not started |
| 8 | Automation + analytics | Not started |
| 9 | Commercial launch | Not started |
