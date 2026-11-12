# syntax=docker/dockerfile:1.7
#
# AI LeadFlow API image. Build context: apps/api
#   docker build -t leadflow-api apps/api
#
# One image, three uses (the command decides):
#   API server  (default CMD)         uvicorn app.main:app
#   Migrations  (one-off, owner role) python -m app.db.bootstrap && alembic upgrade head
#   Worker      (Stage 2+)            celery ...
#
# The image contains no secrets and no .env file: all settings come from
# environment variables at run time. The API container must only receive the
# runtime role credentials (APP_DB_*), never the owner role (POSTGRES_USER/PASSWORD).
#
# Networks that intercept TLS (corporate proxies) can supply their CA bundle as
# an optional build secret; it is used only while downloading packages and is
# never written into the image:
#   docker build --secret id=extra_ca,src=/path/to/ca.pem -t leadflow-api apps/api

ARG PYTHON_IMAGE=python:3.13-slim-trixie

# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS build

# uv from PyPI at the version used in development (see docs/SETUP_GUIDE.md).
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir --disable-pip-version-check uv==0.11.32

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first (cached until pyproject.toml / uv.lock change).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_JSON=true

RUN groupadd --system --gid 10001 leadflow \
 && useradd --system --uid 10001 --gid leadflow --home-dir /app --no-create-home \
      --shell /usr/sbin/nologin leadflow

WORKDIR /app
# Code and virtualenv stay owned by root: the app user can read and run them
# but cannot modify them.
COPY --from=build /app /app

USER leadflow
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
