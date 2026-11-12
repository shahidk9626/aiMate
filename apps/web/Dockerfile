# syntax=docker/dockerfile:1.7
#
# AI LeadFlow web image (Next.js standalone server).
# Build context: the REPOSITORY ROOT (pnpm workspace + lockfile live there):
#   docker build -f apps/web/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.example.com -t leadflow-web .
#
# NEXT_PUBLIC_API_URL is inlined into the browser bundle at build time, so an
# image is built per environment. Never pass secrets as NEXT_PUBLIC_* values.
#
# Networks that intercept TLS can pass their CA bundle as an optional build
# secret (used only during install/build, never stored in the image):
#   --secret id=extra_ca,src=/path/to/ca.pem

ARG NODE_IMAGE=node:22-trixie-slim

# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS deps
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH
WORKDIR /repo

# Workspace manifests first (cached until dependencies change).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    corepack enable \
 && pnpm install --frozen-lockfile --filter @leadflow/web... --store-dir /pnpm/store

# ---------------------------------------------------------------------------
FROM deps AS build
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY apps/web apps/web
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    pnpm --filter @leadflow/web build

# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app

# Standalone server mirrors the monorepo layout (outputFileTracingRoot = repo root).
# Files stay root-owned: the server can read but not modify them.
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
# The Next.js cache directory must be writable at runtime.
RUN mkdir -p apps/web/.next/cache && chown -R node:node apps/web/.next/cache

USER node
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["node", "apps/web/server.js"]
