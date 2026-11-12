# Database Schema

**Status: baseline revision `0001` applied (no tables yet). Tables below are PROPOSED (v1.1, approved design).** Based on LLD v1.0 §3 with the corrections in `ARCHITECTURE_DECISIONS.md` Part 1. Once a table is migrated, this file records the real state and the Alembic revision.

## Applied migrations

| Revision | File | Content |
|---|---|---|
| `0001` | `apps/api/alembic/versions/0001_baseline.py` | `citext` extension; `REVOKE CREATE ON SCHEMA public FROM PUBLIC`; app role `USAGE` on `public`; default privileges so the app role gets `SELECT, INSERT, UPDATE, DELETE` on every future table and `USAGE, SELECT` on sequences. Creates the app role `NOLOGIN` if bootstrap has not run yet. |

## Database roles (ADR-020)

| Role | Purpose | Attributes | Privileges |
|---|---|---|---|
| `leadflow_owner` (`POSTGRES_USER`) | Owns schema; runs Alembic and bootstrap | Local docker: superuser (image default). Production: database owner, **not** superuser | All |
| `leadflow_app` (`APP_DB_USER`) | API and worker at runtime | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` | DML on tables via default privileges; no DDL; cannot read `alembic_version` |
| `leadflow_app_test` | Integration tests only, dropped after the run | Same as app role | Same |

Created/updated by `uv run python -m app.db.bootstrap` (idempotent; also run after changing `APP_DB_PASSWORD`).

## Migration conventions

- Revision ids are sequential 4-digit numbers: `uv run alembic revision --autogenerate --rev-id 0002 -m "create identity tables"`.
- One transaction per migration file.
- Every tenant-owned table's migration calls `enable_tenant_rls_sql(table)` from `app.db.rls` in `upgrade()` and `disable_tenant_rls_sql(table)` in `downgrade()`.
- `downgrade()` is written and tested for every revision (the test suite runs base → head → base → head).
- A test fails if models and migrations drift apart (`compare_metadata` must be empty).

## Conventions

- PostgreSQL, extension `citext`.
- Primary keys: `id UUID` (UUIDv7, app-generated).
- `created_at`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` on every table unless noted.
- Enumerations: `VARCHAR` + `CHECK` (ADR-009).
- Tenant-owned tables: `tenant_id UUID NOT NULL → tenants(id)`, `UNIQUE(tenant_id, id)`, RLS enabled and forced (ADR-006). Child references use composite FKs `(tenant_id, x_id)` (ADR-007).
- Every FK column is indexed. List endpoints get `(tenant_id, <sort column> DESC, id)` indexes for cursor pagination.

## Migration 1 — Stage 2: identity and tenancy

### users (global)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | CITEXT | UNIQUE |
| password_hash | TEXT | Argon2id |
| full_name | VARCHAR(200) | |
| is_active | BOOLEAN | default true |
| is_platform_admin | BOOLEAN | default false |
| email_verified_at | TIMESTAMPTZ NULL | |
| last_login_at | TIMESTAMPTZ NULL | |

### tenants (global)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR(200) | |
| slug | CITEXT | UNIQUE |
| timezone | VARCHAR(64) | IANA name, default `UTC` |
| locale | VARCHAR(16) | default `en` |
| status | VARCHAR | CHECK in (`trial`,`active`,`suspended`,`cancelled`) |
| settings | JSONB | business profile, working hours |

### memberships (tenant-owned)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| tenant_id | UUID FK | |
| user_id | UUID FK → users | |
| role | VARCHAR | CHECK in (`owner`,`admin`,`agent`) |
| status | VARCHAR | CHECK in (`active`,`disabled`) |

Constraints: `UNIQUE(tenant_id, user_id)` (also the target of assignee FKs). Index `(user_id)`. Service rule: a tenant always keeps at least one owner.

### auth_sessions (global, per user)
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → users | indexed |
| family_id | UUID | all rotations of one login share it |
| refresh_token_hash | BYTEA | UNIQUE, SHA-256 of the opaque token |
| expires_at | TIMESTAMPTZ | |
| rotated_at / revoked_at | TIMESTAMPTZ NULL | reuse of a rotated token revokes the family |
| user_agent, ip | VARCHAR / INET NULL | |

### password_reset_tokens (global)
`id`, `user_id FK`, `token_hash BYTEA UNIQUE`, `expires_at`, `used_at NULL`. Single use, short expiry.

### invitations (tenant-owned)
`id`, `tenant_id`, `email CITEXT`, `role`, `token_hash BYTEA UNIQUE`, `invited_by_user_id`, `expires_at`, `accepted_at NULL`. Partial unique `(tenant_id, email) WHERE accepted_at IS NULL`.

### audit_logs (tenant_id nullable)
`id`, `tenant_id NULL`, `actor_user_id NULL`, `action VARCHAR`, `resource_type VARCHAR`, `resource_id UUID NULL`, `metadata JSONB`, `ip INET NULL`, `created_at`. Append-only (no UPDATE/DELETE grant to the app role). Index `(tenant_id, created_at DESC)`.

## Migration 2 — Stage 3: CRM

### contacts
`id`, `tenant_id`, `full_name NULL`, `email CITEXT NULL`, `phone VARCHAR(32) NULL` (E.164), `metadata JSONB`.
Indexes: `(tenant_id, email)`, `(tenant_id, phone)`, `(tenant_id, created_at DESC, id)`. Email/phone are not unique: they are optional and customer-typed.

### leads
| Column | Type | Notes |
|---|---|---|
| id, tenant_id | | |
| contact_id | UUID | composite FK → contacts |
| assigned_user_id | UUID NULL | composite FK `(tenant_id, assigned_user_id)` → memberships`(tenant_id, user_id)` |
| title | VARCHAR(200) | |
| status | VARCHAR | CHECK in (`new`,`contacted`,`qualified`,`won`,`lost`) |
| priority | VARCHAR | CHECK in (`low`,`medium`,`high`), default `medium` |
| source | VARCHAR | CHECK in (`instagram`,`facebook`,`website`,`manual`) |
| estimated_value | NUMERIC(12,2) NULL | |
| currency | CHAR(3) NULL | ISO 4217 (INR/USD/GBP markets) |
| qualification | JSONB | AI-extracted structured fields |
| closed_at | TIMESTAMPTZ NULL | |

Indexes: `(tenant_id, status, created_at DESC)`, `(tenant_id, assigned_user_id)`, `(tenant_id, contact_id)`.
Rule: one open lead per contact — partial unique `(tenant_id, contact_id) WHERE status NOT IN ('won','lost')`.

### lead_notes
`id`, `tenant_id`, `lead_id`, `author_user_id`, `body TEXT`.

### tasks
`id`, `tenant_id`, `lead_id NULL`, `assigned_user_id NULL`, `title`, `due_at NULL`, `status CHECK in (open, done, cancelled)`, `created_by` (`user` | `ai`). Index `(tenant_id, assigned_user_id, status, due_at)`.

## Migration 3 — Stage 4/5: channels and inbox

### channels
| Column | Type | Notes |
|---|---|---|
| id, tenant_id | | |
| provider | VARCHAR | CHECK in (`website`,`instagram`,`facebook`) |
| display_name | VARCHAR(200) | |
| external_account_id | VARCHAR NULL | Meta page / IG account id |
| public_key | VARCHAR NULL | UNIQUE; website widget key |
| allowed_origins | TEXT[] | website only |
| credentials_ciphertext | BYTEA NULL | envelope-encrypted (ADR-013) |
| credentials_key_version | SMALLINT NULL | |
| status | VARCHAR | CHECK in (`pending`,`active`,`error`,`disconnected`) |
| settings | JSONB | |

Constraint: partial unique `(provider, external_account_id) WHERE status <> 'disconnected' AND external_account_id IS NOT NULL` — **global, not per tenant** (review finding I1).

### contact_identities
`id`, `tenant_id`, `contact_id`, `channel_id`, `external_id VARCHAR` (IG-scoped id, page-scoped id, or widget visitor id), `profile JSONB`.
Constraint: `UNIQUE(tenant_id, channel_id, external_id)`.

### conversations
| Column | Type | Notes |
|---|---|---|
| id, tenant_id | | |
| channel_id, contact_id | UUID | composite FKs |
| lead_id | UUID NULL | composite FK |
| external_thread_id | VARCHAR NULL | |
| status | VARCHAR | CHECK in (`open`,`pending`,`closed`) |
| handling_mode | VARCHAR | CHECK in (`ai`,`human`), default `ai` |
| assigned_user_id | UUID NULL | composite FK → memberships |
| last_message_at | TIMESTAMPTZ | |
| last_inbound_at | TIMESTAMPTZ NULL | needed for provider messaging windows |
| unread_count | INTEGER | default 0 |

Constraints: partial unique `(tenant_id, channel_id, external_thread_id) WHERE external_thread_id IS NOT NULL`. Index `(tenant_id, status, last_message_at DESC, id)`.

### messages
| Column | Type | Notes |
|---|---|---|
| id, tenant_id | | |
| conversation_id | UUID | composite FK |
| channel_id | UUID | denormalised for the dedupe index |
| provider_message_id | VARCHAR NULL | |
| client_message_id | VARCHAR NULL | widget idempotency key |
| direction | VARCHAR | CHECK in (`inbound`,`outbound`) |
| sender_type | VARCHAR | CHECK in (`customer`,`ai`,`agent`,`system`) |
| sender_user_id | UUID NULL | set when `agent` |
| body | TEXT | |
| payload | JSONB | attachments, provider extras |
| delivery_status | VARCHAR | CHECK in (`received`,`queued`,`sent`,`delivered`,`failed`) |
| error_code | VARCHAR NULL | provider error on failure |

Constraints: partial unique `(channel_id, provider_message_id)` and `(conversation_id, client_message_id)` where not null. Index `(tenant_id, conversation_id, created_at, id)`. No `updated_at` semantics beyond delivery status.

### conversation_notes
`id`, `tenant_id`, `conversation_id`, `author_user_id`, `body TEXT`. Separate from `messages` so a note cannot be delivered to a customer.

### webhook_events (tenant_id nullable until resolved)
`id`, `provider`, `dedupe_key VARCHAR`, `tenant_id NULL`, `channel_id NULL`, `payload JSONB`, `status CHECK in (received, processing, processed, failed)`, `attempts`, `last_error NULL`, `received_at`, `processed_at NULL`.
Constraint: `UNIQUE(provider, dedupe_key)`. Processed payloads purged after the retention window.

### outbox_events
`id`, `tenant_id NULL`, `event_type VARCHAR`, `payload JSONB`, `status CHECK in (pending, dispatched, failed)`, `attempts`, `available_at`, `dispatched_at NULL`.
Index: partial `(available_at) WHERE status = 'pending'`.

## Later migrations (outline only; designed at their stage)

| Stage | Tables |
|---|---|
| 6 AI | `ai_settings` (tone, allowed actions, thresholds), `knowledge_sources`, `knowledge_chunks` (+ embeddings), `faqs`, `ai_runs` (input refs, output, confidence, decision), `ai_usage` (tokens, cost) |
| 8 Automation / analytics | `automation_rules`, `automation_runs`, `notifications`, daily metric rollups |
| 9 Commercial | `plans`, `subscriptions`, `usage_counters`, `invoices` (provider references) |

## Row Level Security template

Implemented in `apps/api/app/db/rls.py` (single source for migrations and tests):

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

With the setting unset (or reset to an empty string) the comparison is NULL, so the policy fails closed: no rows visible, no rows writable.

The setting is applied per transaction by `app.db.tenant.set_tenant(session, tenant_id)` → `SELECT set_config('app.tenant_id', :id, true)` (bound parameter; transaction-local, so pooled connections never carry a tenant forward).

Verified by `tests/integration/test_tenant_isolation.py`: tenants see only their rows; no context sees nothing and cannot insert; cannot insert, move or modify rows of another tenant; context does not survive commit on the same pooled connection; async and sync sessions both enforce it.
