# Development Progress

## Current state

**Milestone:** Stage 1 — Foundation
**Status:** Step 1 of 5 complete. Branch `stage-1/foundation`.
**Next:** Stage 1, step 2 — FastAPI application skeleton (see below).

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

## Exact next task

**Stage 1, step 2 — FastAPI application skeleton** in `apps/api`:
1. `pyproject.toml` managed by `uv`, Python 3.13; runtime deps: fastapi, uvicorn, pydantic-settings, structlog; dev deps: pytest, httpx, ruff, mypy.
2. `app/main.py` app factory; `app/core/config.py` typed settings from env; `app/core/logging.py` JSON logs without PII; request-id middleware; standard error envelope.
3. `GET /healthz` (liveness). `/readyz` (DB + Redis) comes in step 3 when the DB layer exists.
4. Tests: health endpoint, request-id header, error envelope, settings validation.
5. Run ruff, mypy and pytest; update docs; stop and report.

Remaining Stage 1 steps:
- Step 3: SQLAlchemy 2.1 + psycopg 3 engine/session, Alembic baseline, DB roles (owner vs RLS-restricted app role), `/readyz`.
- Step 4: Next.js + TypeScript + Tailwind scaffold with a page that calls the health endpoint.
- Step 5: API/web Dockerfiles, full `docker compose up`, HLD/LLD v1.1, Stage 1 sign-off.

## Stage tracker

| Stage | Scope | Status |
|---|---|---|
| 0 | Architecture review | Done, approved |
| 1 | Foundation | In progress — step 1 of 5 done |
| 2 | Auth + multi-tenancy | Not started |
| 3 | CRM | Not started |
| 4 | Unified inbox | Not started |
| 5 | Website widget | Not started |
| 6 | AI engine | Not started |
| 7 | Instagram + Facebook | Not started |
| 8 | Automation + analytics | Not started |
| 9 | Commercial launch | Not started |
