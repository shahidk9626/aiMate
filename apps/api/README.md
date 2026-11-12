# AI LeadFlow API

FastAPI service (and, from Stage 2+, the Celery worker). Python 3.13, managed with [uv](https://docs.astral.sh/uv/).

## Commands (run from `apps/api`)

| Task | Command |
|---|---|
| Install dependencies | `uv sync` |
| Run the API (reload) | `uv run uvicorn app.main:app --reload --no-access-log` |
| Tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check (strict) | `uv run mypy` |

`--no-access-log` is required: the app writes its own access log line without query strings.

## Layout

```
app/
├── main.py              # create_app() factory
├── core/
│   ├── config.py        # typed settings from env (pydantic-settings)
│   ├── logging.py       # structlog JSON logging, redaction
│   ├── request_context.py  # X-Request-ID + access log (pure ASGI)
│   └── errors.py        # AppError hierarchy + error envelope handlers
└── api/
    ├── health.py        # /healthz (root, unversioned)
    └── v1/router.py     # /api/v1 product routes
tests/
```

Rules: route handlers stay thin; business logic lives in `app/modules/<module>/service.py` (from Stage 2). Raise `AppError` subclasses for client errors; never build error JSON by hand.
