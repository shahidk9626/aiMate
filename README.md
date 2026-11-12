# AI LeadFlow

AI-powered enquiry automation and unified CRM for businesses. Instagram, Facebook Messenger and website enquiries flow into one workspace, where an AI agent answers from the business's approved knowledge, qualifies the lead, and hands over to a person when needed.

**Status:** Stage 1 (Foundation) in progress. See [`docs/DEVELOPMENT_PROGRESS.md`](docs/DEVELOPMENT_PROGRESS.md).

## Repository layout

```
.
├── apps/
│   ├── api/        # FastAPI service + Celery worker (Python)        — Stage 1, steps 2–3 ✓
│   ├── web/        # Next.js dashboard (TypeScript, Tailwind)         — Stage 1, step 4 ✓
│   └── widget/     # Embeddable website chat widget                  — Stage 5
├── packages/
│   └── contracts/  # TypeScript types generated from the OpenAPI spec — Stage 2+
├── infra/
│   └── docker-compose.yml   # PostgreSQL + Redis for local development
└── docs/           # Architecture, decisions, schema, API, setup, progress
```

Directories appear when their step is built; nothing is scaffolded ahead of time.

## Quick start

Prerequisites: Docker, Python 3.13 + [uv](https://docs.astral.sh/uv/), Node.js 22.12+ with pnpm (`corepack enable`).

1. Settings: `cp .env.example .env`, then replace every `change-me` value.
2. Data services: `docker compose --env-file .env -f infra/docker-compose.yml up -d`
3. API (from `apps/api`): `uv sync`, `uv run python -m app.db.bootstrap`, `uv run alembic upgrade head`, then `uv run uvicorn app.main:app --reload --no-access-log`
4. Web (from the repo root): `pnpm install`, then `pnpm dev:web`
5. Open **http://localhost:3000** → "View system status".

Step-by-step instructions and troubleshooting: [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md).

## Documentation

| File | Purpose |
|---|---|
| [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) | Product vision, requirements, stack — start here |
| [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) | Architecture review and decision log |
| [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) | Tables, constraints, indexes, RLS |
| [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) | Endpoints and response formats |
| [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md) | Tooling, environment variables, local run |
| [`docs/DEVELOPMENT_PROGRESS.md`](docs/DEVELOPMENT_PROGRESS.md) | Milestones and the exact next task |
| [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) | Bugs, limitations, pending decisions |
