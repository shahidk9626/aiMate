# Setup Guide

**Status: local PostgreSQL and Redis are runnable (Stage 1, step 1).** The API and web app do not exist yet. Commands are added here as each piece is built and verified; this file must never describe a step that has not been run successfully.

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

## Environment variables in use now (`.env.example`)

| Variable | Used by | Notes |
|---|---|---|
| `APP_ENV` | all | `local` |
| `POSTGRES_DB` | compose | Database name, default `leadflow` |
| `POSTGRES_USER` | compose | Owner role, default `leadflow_owner`. Migrations only once the app role exists (step 3) |
| `POSTGRES_PASSWORD` | compose | Secret. Compose refuses to start without it |
| `POSTGRES_PORT` | compose | Host port, default `5432`, bound to 127.0.0.1 |
| `REDIS_PASSWORD` | compose | Secret. Redis requires auth even locally |
| `REDIS_PORT` | compose | Host port, default `6379`, bound to 127.0.0.1 |

## Environment variables (planned)

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

### 1. Data services (verified 2026-11-12)

Prerequisite: Docker with the Compose plugin. All commands run from the repository root.

Create your local environment file, then replace every `change-me` value with your own password:

```bash
cp .env.example .env
```

Start PostgreSQL and Redis:

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d
```

Both services should show `(healthy)` within about 10 seconds:

```bash
docker compose --env-file .env -f infra/docker-compose.yml ps
```

Optional connection check (needs `psql` on your machine; enter `POSTGRES_PASSWORD` when prompted):

```bash
psql -h 127.0.0.1 -U leadflow_owner -d leadflow -c "select version();"
```

Stop the services (data is kept in Docker volumes):

```bash
docker compose --env-file .env -f infra/docker-compose.yml down
```

Delete all local data as well (destructive):

```bash
docker compose --env-file .env -f infra/docker-compose.yml down -v
```

Troubleshooting:
- `required variable … is missing a value`: `.env` is missing or a variable is empty.
- Port already in use: change `POSTGRES_PORT` / `REDIS_PORT` in `.env`.
- Changing `POSTGRES_PASSWORD` after the first start has no effect on the existing volume; run `down -v` to re-initialise (deletes data).

### 2. API, worker and web

To be written as each is built (Stage 1, steps 2–5).
