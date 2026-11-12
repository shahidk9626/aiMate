# Setup Guide

**Status: nothing is runnable yet.** The repository contains documentation only. Commands are added here as each piece is built and verified; this file must never describe a step that has not been run successfully.

## Required tooling (planned)

| Tool | Version line | Purpose |
|---|---|---|
| Python | 3.13 | API and worker |
| uv | latest | Python dependencies and lockfile |
| Node.js | 22 LTS | Web app and widget |
| pnpm | latest | JS workspaces |
| Docker + Compose | current | PostgreSQL, Redis, full local stack |
| PostgreSQL | 17 (container) | Database |
| Redis | 7+ (container) | Celery broker, pub/sub, rate limits |

## Planned dependencies

Latest stable on PyPI/npm as checked on 2026-11-12. Exact versions are pinned by lockfiles when installed, and compatibility is confirmed by the test suite at that point.

Backend runtime:
| Package | Latest seen | Why |
|---|---|---|
| fastapi | 0.162.x | HTTP framework |
| uvicorn | 0.54.x | ASGI server |
| pydantic / pydantic-settings | 2.14.x / 2.16.x | Validation, typed config from env |
| sqlalchemy | 2.1.x | ORM (2.x style) |
| alembic | 1.20.x | Migrations |
| psycopg | 3.3.x | PostgreSQL driver, sync + async |
| celery | 5.7.x | Background jobs |
| redis | 8.1.x | Redis client |
| argon2-cffi | 25.1.x | Argon2id password hashing |
| pyjwt | 2.15.x | Access tokens |
| cryptography | 50.x | Credential envelope encryption |
| httpx | 0.28.x | Outbound HTTP (Meta), test client |
| structlog | 26.x | Structured JSON logging |
| openai | 3.x | First LLM adapter (Stage 6, not before) |

Backend dev: pytest 9.x, pytest-asyncio, ruff, mypy.

Frontend: Next.js 16.x, React 19.x, Tailwind CSS 4.x, TypeScript (version as pinned by the Next.js scaffold — TypeScript 7.0 is very new and is adopted only if the Next.js toolchain supports it).

## Environment variables (planned — `.env.example` is created in Stage 1)

| Variable | Used by | Notes |
|---|---|---|
| `APP_ENV` | api, worker | `local` / `staging` / `production` |
| `DATABASE_URL` | api, worker | App role, no BYPASSRLS |
| `DATABASE_MIGRATION_URL` | alembic | Owner role, migrations only |
| `REDIS_URL` | api, worker | |
| `JWT_SECRET` | api | Secret |
| `CREDENTIALS_MASTER_KEY`, `CREDENTIALS_KEY_VERSION` | api, worker | Secret; channel token encryption |
| `WEB_ORIGIN`, `COOKIE_DOMAIN` | api | CORS/CSRF and cookies |
| `EMAIL_*` | api, worker | Stage 2; provider pending |
| `OPENAI_API_KEY`, `LLM_MODEL` | worker | Stage 6 |
| `META_APP_ID`, `META_APP_SECRET`, `META_VERIFY_TOKEN` | api, worker | Stage 7 |
| `NEXT_PUBLIC_API_URL` | web | Only non-secret values may be `NEXT_PUBLIC_` |

Secrets live in untracked `.env` files locally and in the host's secret store in production. `.env` is git-ignored; `.env.example` holds names and safe placeholders only.

## Local run

To be written in Stage 1 once `docker compose up` and the health endpoints are verified.
