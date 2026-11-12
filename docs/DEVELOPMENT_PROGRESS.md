# Development Progress

## Current state

**Milestone:** Stage 1 — Foundation
**Status:** Steps 1–2 of 5 complete. Branch `stage-1/foundation`.
**Next:** Stage 1, step 3 — database layer (see below).

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

## Exact next task

**Stage 1, step 3 — database layer** in `apps/api`:
1. New runtime deps (explained at the time): `sqlalchemy` 2.1, `psycopg[binary]` 3.3, `alembic` 1.20, `redis` 8.1; dev: `pytest-asyncio`.
2. Settings: `DATABASE_URL` (app role), `DATABASE_MIGRATION_URL` (owner role), `REDIS_URL` as `SecretStr`-backed values.
3. Database roles: owner (migrations) vs `leadflow_app` (runtime, no `BYPASSRLS`, no DDL), created by the baseline migration; docker init or documented bootstrap for the app role password.
4. `app/db/`: async engine + session dependency, sync engine for workers, declarative `Base` with naming conventions, UUIDv7 + timestamp mixins, `tenant_session()` that runs `SET LOCAL app.tenant_id`.
5. Alembic configured for the owner URL; baseline migration enables `citext`, creates roles and grants.
6. `GET /readyz` checking DB and Redis with short timeouts.
7. Integration tests against the compose PostgreSQL/Redis (skipped with a clear message if unavailable); stop and report.

Remaining Stage 1 steps:
- Step 4: Next.js + TypeScript + Tailwind scaffold with a page that calls the health endpoint.
- Step 5: API/web Dockerfiles, full `docker compose up`, HLD/LLD v1.1, Stage 1 sign-off.

## Stage tracker

| Stage | Scope | Status |
|---|---|---|
| 0 | Architecture review | Done, approved |
| 1 | Foundation | In progress — steps 1–2 of 5 done |
| 2 | Auth + multi-tenancy | Not started |
| 3 | CRM | Not started |
| 4 | Unified inbox | Not started |
| 5 | Website widget | Not started |
| 6 | AI engine | Not started |
| 7 | Instagram + Facebook | Not started |
| 8 | Automation + analytics | Not started |
| 9 | Commercial launch | Not started |
