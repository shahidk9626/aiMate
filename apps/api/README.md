# AI LeadFlow API

FastAPI service (and, from Stage 2+, the Celery worker). Python 3.13, managed with [uv](https://docs.astral.sh/uv/).

## Commands (run from `apps/api`)

| Task | Command |
|---|---|
| Install dependencies | `uv sync` |
| Run the API (reload) | `uv run uvicorn app.main:app --reload --no-access-log` |
| Create/update runtime DB role | `uv run python -m app.db.bootstrap` |
| Apply migrations | `uv run alembic upgrade head` |
| New migration | `uv run alembic revision --autogenerate --rev-id 0002 -m "..."` |
| Tests (unit + integration) | `uv run pytest` |
| Unit tests only | `uv run pytest -m "not integration"` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check (strict) | `uv run mypy` |

`--no-access-log` is required: the app writes its own access log line without query strings.

## Layout

```
app/
├── main.py              # create_app() factory + lifespan
├── core/
│   ├── config.py        # typed settings from env (pydantic-settings)
│   ├── logging.py       # structlog JSON logging, redaction
│   ├── request_context.py  # X-Request-ID + access log (pure ASGI)
│   ├── errors.py        # AppError hierarchy + error envelope handlers
│   └── redis.py         # async Redis client factory
├── db/
│   ├── base.py          # DeclarativeBase, naming conventions, mixins
│   ├── ids.py           # UUIDv7
│   ├── engine.py        # async (API) + sync (worker) engines, session factories
│   ├── session.py       # DbSession dependency (one transaction per request)
│   ├── tenant.py        # set_tenant(): transaction-local RLS context
│   ├── rls.py           # RLS policy SQL used by migrations
│   ├── models.py        # model registry for Alembic
│   └── bootstrap.py     # create/update restricted runtime role
└── api/
    ├── health.py        # /healthz, /readyz (root, unversioned)
    └── v1/router.py     # /api/v1 product routes
alembic/                 # migrations (run as owner role)
tests/                   # unit tests
tests/integration/       # real PostgreSQL/Redis; disposable leadflow_test DB
```

Rules: route handlers stay thin; business logic lives in `app/modules/<module>/service.py` (from Stage 2). Raise `AppError` subclasses for client errors; never build error JSON by hand.
