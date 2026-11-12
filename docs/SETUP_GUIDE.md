# Setup Guide

**Status: Stage 1 complete.** Run the parts individually on your machine (sections 1–5, best for development), or the whole stack in Docker with one command (section 6). Commands are added here as each piece is built and verified; this file must never describe a step that has not been run successfully.

## Required tooling (planned)

| Tool | Version line | Purpose |
|---|---|---|
| Python | 3.13 | API and worker |
| uv | latest | Python dependencies and lockfile |
| Node.js | 22.12+ | Web app and widget (Vitest 5 / jsdom 31 need ≥ 22.12) |
| pnpm | 10.x (pinned in root `package.json`) | JS workspaces; enable with `corepack enable` |
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

Backend dev: pytest 9.x, httpx2 2.16.x (Starlette TestClient, ADR-019), ruff 0.17.x, mypy 2.4.x. pytest-asyncio is added only when async DB tests need it (step 3).

**Installed and locked** (`apps/api/uv.lock`): fastapi 0.162.5, starlette 1.10.0, uvicorn 0.54.0, pydantic 2.14.3, pydantic-settings 2.16.2, structlog 26.1.0, sqlalchemy 2.1.8 (`asyncio` extra → greenlet 3.5.6), psycopg 3.3.9 (binary), alembic 1.20.1, redis 8.1.0, pytest 9.2.0 (+ anyio plugin for async tests), httpx2 2.16.0, ruff 0.17.4, mypy 2.4.1. Data services: PostgreSQL 17.11, Redis 8.10.

Frontend, **installed and locked** (`pnpm-lock.yaml`): next 16.4.6, react / react-dom 19.3.0, tailwindcss 4.3.3 (+ `@tailwindcss/turbopack`), typescript 5.x, eslint 9.39 + eslint-config-next 16.4.6; tests: vitest 5.1.0, @vitejs/plugin-react 6.3.0, jsdom 31.0.0, @testing-library/react 16.3.3, @testing-library/dom 10.4.2, @testing-library/jest-dom 7.0.1. TypeScript 7 and ESLint 10 are not used: the Next.js scaffold pins 5 and 9 (ADR-021).

## Environment variables in use now

One root `.env` (copied from `.env.example`) serves docker compose and the API. The API reads real environment variables first, then `apps/api/.env`, then the root `.env`.

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `local` | `local`, `test`, `staging`, `production`. Production hides the API docs |
| `LOG_LEVEL` | `INFO` | `DEBUG` … `CRITICAL` |
| `LOG_JSON` | auto | Human-readable logs in `local`, JSON everywhere else |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` | `127.0.0.1` / `5432` / `leadflow` | |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | `leadflow_owner` / — | Owner. Migrations + bootstrap only; do not give to API/worker outside local |
| `APP_DB_USER` / `APP_DB_PASSWORD` | `leadflow_app` / — | Runtime role. Password **required** in staging/production |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | `127.0.0.1` / `6379` / `0` / — | Password **required** in staging/production |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `5` / `5` | Per process |
| `DB_CONNECT_TIMEOUT_SECONDS` | `5` | |
| `READINESS_TIMEOUT_SECONDS` | `2` | Per `/readyz` check |
| `SESSION_IDLE_DAYS` / `SESSION_ABSOLUTE_DAYS` | `7` / `30` | Login session lifetime (Stage 2) |
| `SESSION_TOUCH_MINUTES` | `5` | How often a session's last-seen time is updated |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Larger request bodies get 413 |
| `TRUSTED_PROXY` | `none` | `cloudflare` only when the API is reachable exclusively through Cloudflare |
| `WEB_ORIGIN` | `http://localhost:3000` | The single browser origin allowed by CORS. Must be a public `https` origin in staging/production |

Web app (`apps/web/.env.local`, see `apps/web/.env.example`): `NEXT_PUBLIC_API_URL`, default `http://localhost:8000` in development, **required** for production builds and baked in at build time. Only non-secret values may use `NEXT_PUBLIC_`.

Full Docker stack (`--profile app`) also uses `API_PORT` (default `8000`) and `WEB_PORT` (default `3000`); the API's `WEB_ORIGIN` and the web build's API URL are derived from them.

Compose uses `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `REDIS_PASSWORD`, `REDIS_PORT`.

## Environment variables (planned)

| Variable | Used by | Notes |
|---|---|---|
| `JWT_SECRET` | api | Secret. Stage 2 |
| `CREDENTIALS_MASTER_KEY`, `CREDENTIALS_KEY_VERSION` | api, worker | Secret; channel token encryption |
| `COOKIE_DOMAIN` | api | Session cookies. Stage 2 |
| `EMAIL_*` | api, worker | Stage 2; provider pending |
| `OPENAI_API_KEY`, `LLM_MODEL` | worker | Stage 6 |
| `META_APP_ID`, `META_APP_SECRET`, `META_VERIFY_TOKEN` | api, worker | Stage 7 |

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

### 2. API (verified 2026-11-12)

Prerequisites: Python 3.13 and [uv](https://docs.astral.sh/uv/). All commands from `apps/api`.

Install dependencies (creates `apps/api/.venv` from the lockfile):

```bash
uv sync
```

Run the API with auto-reload:

```bash
uv run uvicorn app.main:app --reload --no-access-log
```

Check it: http://127.0.0.1:8000/healthz returns `{"status":"ok"}`; Swagger UI is at http://127.0.0.1:8000/api/v1/docs.

### 3. Database role and migrations (verified 2026-11-12)

Needs the data services from section 1 running and `APP_DB_PASSWORD` set in the root `.env`. From `apps/api`.

Create (or update the password of) the restricted runtime role — once per environment, and again whenever `APP_DB_PASSWORD` changes:

```bash
uv run python -m app.db.bootstrap
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Check the current revision:

```bash
uv run alembic current
```

With the API running, http://127.0.0.1:8000/readyz returns `200` with `"database":"ok","redis":"ok"`, or `503` naming the dependency that is down.

If you created `.env` in step 1, add the new keys from `.env.example` (`POSTGRES_HOST`, `APP_DB_USER`, `APP_DB_PASSWORD`, `REDIS_HOST`, `REDIS_DB`, `LOG_LEVEL`). Existing database data is unaffected.

### 4. Tests and quality checks

Unit and integration tests (integration tests need section 1 running; they create and drop their own `leadflow_test` database and never touch `leadflow`):

```bash
uv run pytest
```

Unit tests only (no Docker needed):

```bash
uv run pytest -m "not integration"
```

Lint, format and strict type checks (all must pass before committing):

```bash
uv run ruff check . && uv run ruff format --check .
```

```bash
uv run mypy
```

All environment variables are listed in "Environment variables in use now" above.

### 5. Web app (verified 2026-11-12)

Prerequisites: Node.js 22.12 or newer, and pnpm. pnpm ships with Node through corepack:

```bash
corepack enable
```

Install the JavaScript dependencies (from the repository root):

```bash
pnpm install
```

Optional: copy `apps/web/.env.example` to `apps/web/.env.local`. Without it the app uses `http://localhost:8000` as the API address in development.

Start the dev server (from the repository root), with the API from section 2 running:

```bash
pnpm dev:web
```

Open **http://localhost:3000** and click "View system status". All three services should show "Operational".

Use `localhost`, not `127.0.0.1`: the API only accepts browser requests from `WEB_ORIGIN` (default `http://localhost:3000`). From any other address the status page shows "Could not reach the server" and the browser console shows a CORS error. That is the protection working.

Web checks (from `apps/web`): lint, type check and unit tests in one command:

```bash
pnpm check
```

Production build (the API URL is baked into the build):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm build
```

### 6. Whole stack in Docker (verified 2026-11-12)

Runs PostgreSQL, Redis, migrations, the API and the web app in containers. Nothing but Docker is needed on your machine. Stop any API or web app you started by hand first (they use the same ports), or change `API_PORT` / `WEB_PORT` in `.env`.

From the repository root:

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile app up -d --build
```

The first build takes a few minutes; later builds reuse cached layers. Then open **http://localhost:3000/status**.

What happens, in order: PostgreSQL and Redis start and become healthy → `migrate` creates/updates the app database role and applies migrations, then exits → `api` starts and becomes healthy once `/readyz` passes → `web` starts.

Check the state of every service (`migrate` should show `Exited (0)`):

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile app ps -a
```

Follow the API logs:

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile app logs -f api
```

Stop everything (data is kept):

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile app down
```

Without `--profile app`, compose starts only PostgreSQL and Redis, as in section 1.

Behind a corporate proxy that intercepts HTTPS, builds can fail with certificate errors. Pass your company's CA bundle as a build secret (used only during the build, never stored in the image):

```bash
docker build --secret id=extra_ca,src=/path/to/company-ca.pem -t leadflow-api:local apps/api
```

### 7. Worker

To be written in Stage 2+ when the first background job exists.
