# AI LeadFlow

AI-powered enquiry automation and unified CRM for businesses. Instagram, Facebook Messenger and website enquiries flow into one workspace, where an AI agent answers from the business's approved knowledge, qualifies the lead, and hands over to a person when needed.

**Status:** Stage 1 (Foundation) in progress. See [`docs/DEVELOPMENT_PROGRESS.md`](docs/DEVELOPMENT_PROGRESS.md).

## Repository layout

```
.
├── apps/
│   ├── api/        # FastAPI service + Celery worker (Python)        — Stage 1, step 2
│   ├── web/        # Next.js dashboard (TypeScript, Tailwind)         — Stage 1, step 4
│   └── widget/     # Embeddable website chat widget                  — Stage 5
├── packages/
│   └── contracts/  # TypeScript types generated from the OpenAPI spec — Stage 2+
├── infra/
│   └── docker-compose.yml   # PostgreSQL + Redis for local development
└── docs/           # Architecture, decisions, schema, API, setup, progress
```

Directories appear when their step is built; nothing is scaffolded ahead of time.

## Quick start (local data services)

```bash
cp .env.example .env   # then replace every change-me value
docker compose --env-file .env -f infra/docker-compose.yml up -d
docker compose --env-file .env -f infra/docker-compose.yml ps
```

Full instructions: [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md).

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
