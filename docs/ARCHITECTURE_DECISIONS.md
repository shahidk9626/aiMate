# Architecture Decisions

Status values: **Accepted** (given by product owner or already fixed), **Proposed** (awaiting product-owner approval), **Deferred** (decide at the named stage).

Part 1 is the Day 1 review of HLD/LLD v1.0. Part 2 is the decision log.

---

## Part 1 — Review of HLD v1.0 and LLD v1.0

The overall design is sound: modular monolith, separate worker, durable-before-async ingestion, transactional outbox, typed AI actions, tenant-scoped tables. The findings below are gaps and inconsistencies to correct before code is written.

**All corrections below were approved by the product owner on 2026-11-12.** HLD/LLD HTML revision to v1.1 is scheduled for Stage 1, step 5.

### Inconsistencies

| # | Finding | Correction |
|---|---|---|
| I1 | `channels` is `UNIQUE(tenant_id, provider, external_account_id)`. Two tenants could connect the same Instagram/Facebook account, making webhook → tenant resolution ambiguous and leaking messages across tenants. | Unique on `(provider, external_account_id)` globally for non-disconnected channels. |
| I2 | LLD §5 and §9 depend on an outbox table; the data model has none. | Add `outbox_events` and a relay (ADR-008). |
| I3 | `POST /auth/refresh` is listed as "Authenticated". An expired access token is the reason refresh is called. | Refresh is authorized by the refresh cookie only. |
| I4 | LLD §1 lists logout; the brief requires logout and password reset; no endpoints or tables exist for either. | Add endpoints plus `auth_sessions`, `password_reset_tokens`. |
| I5 | `contacts.external_identity` is a single unindexed column. A person can appear on Instagram, Facebook and the website, and without a unique key contacts cannot be deduplicated safely. | New `contact_identities` table, unique per `(tenant, channel, external_id)`. |
| I6 | `webhook_events UNIQUE(provider, provider_event_id)`. Meta deliveries carry no event id; one delivery batches several entries/messages. | Dedupe key is derived per message (`mid`) or a hash per event; store as `dedupe_key`. |
| I7 | `messages UNIQUE(tenant_id, provider_message_id)`: provider ids are only unique per provider. | Unique on `(channel_id, provider_message_id)` where not null. |
| I8 | `audit_logs.tenant_id` and `resource_id` are mandatory, but logins and platform events have no tenant/resource. | Both nullable. |
| I9 | `assigned_user_id` on leads/conversations has no FK. An agent from another tenant could be assigned. | Composite FK `(tenant_id, assigned_user_id)` → `memberships(tenant_id, user_id)`. |
| I10 | HLD names a "Platform admin" actor; LLD roles are only owner/admin/agent. | `users.is_platform_admin`, separate from tenant roles. |
| I11 | The brief requires lead **priority**; the LLD lead has none. HLD says "stages" (configurable); LLD hardcodes a status enum. | Add `priority`. Keep fixed statuses for MVP (ADR-011). |
| I12 | Human takeover is required, but `conversations.status (open/pending/closed)` cannot express "AI is silenced, human is handling". | Add `handling_mode (ai | human)` separate from status. |
| I13 | Internal notes are required in the inbox; `messages.sender_type` has no way to mark a non-customer-visible note. | `conversation_notes` table, kept out of `messages` so a note can never be sent to a customer by mistake. |
| I14 | Brief Stage 5 includes "AI response integration" but the AI engine is Stage 6. HLD has 5 stages, the brief has 9. | The brief's 9 stages govern. Stage 5 ships against the AI interface with a handoff-only responder; Stage 6 plugs in the real engine. |
| I15 | HLD says "Celery (or ARQ)". | Celery is final. |

### Missing requirements

| # | Gap | Proposal |
|---|---|---|
| M1 | A user can belong to several tenants; nothing says how the active tenant is chosen per request. | ADR-005. |
| M2 | No mechanism for delivering AI/agent replies to the widget or new messages to the inbox in real time. | ADR-010. |
| M3 | Widget security is "validate origin". The `Origin` header is trivially forged outside a browser, and nothing stops a visitor reading another visitor's conversation. | Signed per-visitor session token, public widget key, origin allowlist, rate limit, optional Cloudflare Turnstile. |
| M4 | Cookie auth needs CSRF protection; not mentioned. | ADR-004. |
| M5 | No tables for notes, tasks, knowledge/FAQs, AI settings, AI usage ledger, invitations, automation rules, subscriptions/usage. | Added to the schema roadmap per stage (`DATABASE_SCHEMA.md`). |
| M6 | API list lacks contacts, lead detail, notes/tasks, members/invites, tenant settings, conversation assign/takeover/close, widget public endpoints, health. | `API_CONTRACTS.md`. |
| M7 | No rule for when an inbound message creates a new lead vs. attaches to an existing one. | At most one open lead per contact; a new lead is created only when none is open. |
| M8 | Transactional email is needed for password reset and invitations; no provider chosen. | Decision D6. |
| M9 | Compliance is unaddressed: India DPDP Act, UK GDPR, and US HIPAA for dental clinics and med spas (enquiries may contain health information that would be sent to an LLM provider). | Decision D7. |
| M10 | Meta app review and business verification have long lead times and gate Stage 7. | Product owner starts Meta developer app + business verification in parallel now. Permissions and messaging-window rules to be verified against current Meta docs at Stage 7. |
| M11 | `webhook_events.payload` holds customer PII with no retention rule. | Purge processed payloads after a retention window (30 days proposed). |
| M12 | RLS is "consider". Retrofitting RLS after the data layer exists is expensive. | ADR-006: on from the first migration. |

---

## Part 2 — Decision log

### ADR-001 Modular monolith + separate worker — Accepted
One FastAPI codebase organised by domain module, one Celery worker process sharing the same code. Microservices rejected: no load or team size that justifies the operational cost.

### ADR-002 Python/FastAPI/SQLAlchemy replaces NestJS/Drizzle — Accepted
Decided by product owner. Reason: AI ecosystem fit and typed async APIs.

### ADR-003 Async API, sync workers, one driver (psycopg 3) — Accepted (2026-11-12)
FastAPI uses SQLAlchemy async sessions; Celery tasks are synchronous and use sync sessions. psycopg 3 supports both modes, so there is one driver, one connection URL format and one set of type behaviours.
Alternatives: asyncpg + psycopg2 (two drivers, divergent behaviour); fully sync API (simpler, but webhook and SSE endpoints benefit from async I/O); running asyncio inside Celery tasks (fragile).

### ADR-004 Authentication — Accepted (2026-11-12)
- Passwords: Argon2id (`argon2-cffi`).
- Access token: short-lived JWT (15 min), HttpOnly, Secure, SameSite=Lax cookie.
- Refresh token: opaque random value, stored only as a SHA-256 hash in `auth_sessions`, rotated on every use; reuse of a rotated token revokes the whole session family.
- Web and API are served from the same registrable domain (`app.` / `api.`) so SameSite cookies work.
- CSRF: state-changing requests require a custom header and an `Origin` check.
- Login and password reset responses never reveal whether an email exists.
Alternative: opaque server-side sessions only. Simpler and instantly revocable, but the LLD specifies access + refresh and it scales better to future mobile/API clients.

### ADR-005 Tenant context resolution — Accepted (2026-11-12)
The client sends the active tenant in an `X-Tenant-ID` header. A dependency loads the membership for `(authenticated user, tenant)` on every request; no membership → 404 with a security log entry. The verified `TenantContext(tenant_id, user_id, role)` is the only way services receive a tenant id. Request bodies never carry `tenant_id`.
Alternative: embed tenant in the JWT (requires a token re-issue to switch business, and role changes lag until expiry).

### ADR-006 Row Level Security from the first migration — Accepted (2026-11-12)
- Every tenant-owned table has `tenant_id`, RLS enabled and forced, with a policy `tenant_id = current_setting('app.tenant_id')::uuid`.
- The app connects as a non-owner role without `BYPASSRLS`. Each transaction runs `SET LOCAL app.tenant_id`.
- Pre-tenant paths (login, webhook channel lookup, outbox relay, platform admin) use a separate, narrowly used system session.
- Application-level tenant filters remain mandatory; RLS is the second lock.
- Tests include a cross-tenant suite that must fail closed.
Alternative: application filtering only (one forgotten `WHERE` leaks a customer's data; unacceptable for a commercial product).

### ADR-007 Cross-tenant reference integrity — Accepted (2026-11-12)
Every tenant-owned table has `UNIQUE(tenant_id, id)`; child tables reference parents with composite FKs `(tenant_id, parent_id)`. The database itself rejects a lead pointing at another tenant's contact.

### ADR-008 Transactional outbox — Accepted (2026-11-12)
Domain writes and an `outbox_events` row commit in one transaction. A relay (Celery beat task, `SELECT … FOR UPDATE SKIP LOCKED`) publishes to Celery and marks rows dispatched. Tasks are idempotent, `acks_late=True`, with bounded retries and a dead-letter state. FastAPI `BackgroundTasks` is never used for durable work.

### ADR-009 Enumerations as VARCHAR + CHECK — Accepted (2026-11-12)
Native PostgreSQL ENUM types are awkward to alter in Alembic (adding/removing values, transactions). Python `StrEnum` in code, `VARCHAR` + `CHECK` in the database.

### ADR-010 Real-time delivery via Server-Sent Events — Accepted (2026-11-12)
Dashboard inbox and widget receive new messages over SSE backed by Redis pub/sub, with reconnect + "fetch since cursor" for correctness. Alternatives: polling (simple, laggy, wasteful), WebSockets (bidirectional not needed; harder behind proxies).

### ADR-011 Fixed lead statuses for MVP — Accepted (2026-11-12)
`new, contacted, qualified, won, lost` plus `priority (low, medium, high)`. Configurable per-tenant pipelines are deferred until a pilot client asks; migrating from a fixed status to a `pipeline_stages` table later is straightforward.

### ADR-012 Identifiers and time — Accepted (2026-11-12)
UUIDv7 primary keys generated in the application (time-ordered, better index locality than v4, not guessable in practice for API use). All timestamps `TIMESTAMPTZ` in UTC; tenant timezone applied at presentation.

### ADR-013 Credential encryption — Accepted (2026-11-12)
Channel tokens stored as ciphertext using envelope encryption: per-record data key, wrapped by a master key supplied through the environment (versioned for rotation). Implemented with `cryptography` (AES-256-GCM). Never logged, never returned by the API.

### ADR-014 AI abstraction — Accepted (2026-11-12)
`LLMProvider` protocol with `generate(structured_input) -> structured_output`; OpenAI is the first adapter. Output is validated against a Pydantic schema; actions are an allowlisted typed union executed by backend services under the tenant context. Every call writes to an `ai_usage` ledger (tenant, model, tokens, cost).

### ADR-015 Tooling — Accepted (2026-11-12)
`uv` for Python dependency management and lockfile, `pnpm` workspaces for JS, `ruff` for lint/format, `mypy` for type checks, `structlog` for JSON logs with request id and tenant id (no message bodies or PII).

### ADR-016 Widget as its own package — Accepted (2026-11-12)
`apps/widget` is a small standalone TypeScript bundle (no React/Next.js dependency) loaded by a one-line script tag and rendered in an isolated iframe/shadow root, so it stays small and cannot be broken by host-site CSS.

### ADR-017 Local infrastructure via Docker Compose — Accepted (2026-11-12)
`infra/docker-compose.yml` runs PostgreSQL 17 and Redis 8 (Alpine images) for local development. Ports bind to `127.0.0.1` only. Redis requires a password even locally, so the app is written against an authenticated Redis from day one. Credentials come from the git-ignored root `.env`; the Compose file refuses to start if they are missing. Application services are added to the same file as they are built.

### Deferred
- Vector store for knowledge retrieval (pgvector in the same Postgres is the default candidate) — Stage 6.
- Billing provider (Stripe for US/UK, Razorpay for India are the candidates) — Stage 9.
- Object storage provider (Cloudflare R2 candidate) — Stage 6.
- Configurable pipelines, white-label, WhatsApp — post-MVP.
