# API Contracts

**Status: health probes, error and success envelopes, CSRF/limits, and the Stage 2 authentication endpoints are implemented; everything else is PROPOSED.** Each endpoint is marked Implemented with its request/response schema when it ships. The generated OpenAPI document (`/api/v1/openapi.json`) becomes the machine-readable contract; TypeScript types in `packages/contracts` are generated from it.

## Conventions

- Base path `/api/v1`. JSON only. UTF-8.
- Auth: HttpOnly cookies (access + refresh). State-changing requests need header `X-Requested-With: leadflow` and a trusted `Origin`.
- Tenant: header `X-Tenant-ID: <uuid>` on every tenant-scoped route; verified against membership. Request bodies never contain `tenant_id`.
- Every response carries `X-Request-ID`.
- CSRF (implemented, Stage 2 step 2.2): every `POST/PUT/PATCH/DELETE` under `/api/v1/` must send `X-Requested-With: leadflow`; if the request has an `Origin` header it must equal `WEB_ORIGIN`. Otherwise `403 CSRF_REJECTED`. Exempt: `/api/v1/webhooks/*`, `/api/v1/widget/*` (authenticated by signatures / widget tokens).
- Request size (implemented): bodies over `MAX_REQUEST_BODY_BYTES` (default 1 MB), declared or streamed, get `413 PAYLOAD_TOO_LARGE`.
- Rate limits (mechanism implemented; rules attach to endpoints from step 2.3): `429 RATE_LIMITED` with a `Retry-After` header in seconds.
- Security headers on every response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`; `Cache-Control: no-store` on all `/api/v1` responses.
- Unhandled errors return `500 INTERNAL_ERROR` in the envelope **with** CORS and request-id headers, so browsers see the real error.
- CORS (implemented, Stage 1 step 4): browsers may call the API only from `WEB_ORIGIN` (one origin). Credentials allowed. Methods `GET, POST, PUT, PATCH, DELETE`. Request headers `Content-Type, X-Requested-With, X-Tenant-ID, Idempotency-Key, X-Request-ID`. Exposed: `X-Request-ID`. Preflight cached 10 minutes. Untrusted origins get no CORS headers (preflight `400`).
- Pagination: cursor based — `?limit=50&cursor=<opaque>`.
- Roles: `agent < admin < owner`. "Agent+" means agent or higher.

Success (implemented, `app/core/responses.py`; `next_cursor` arrives with the first paginated list):
```json
{ "data": { }, "meta": { "request_id": "…" } }
```

Error:
```json
{ "error": { "code": "LEAD_NOT_FOUND", "message": "Lead not found.", "details": [] },
  "meta": { "request_id": "…" } }
```

Cross-tenant access returns `404`, never `403`, so record existence is not revealed. Validation errors are `422` with field-level `details`. Rate limiting is `429` with `Retry-After`.

### Error envelope — Implemented (Stage 1, step 2)

| Situation | Status | `error.code` |
|---|---|---|
| Service raises `AppError` subclass | its status | its code (e.g. `LEAD_NOT_FOUND`) |
| Body/query validation fails | 422 | `VALIDATION_ERROR`; `details` = `[{field, message, type}]`, submitted values are **never** echoed |
| Unknown route | 404 | `NOT_FOUND` |
| Wrong method | 405 | `METHOD_NOT_ALLOWED` (+ `Allow` header) |
| Unhandled exception | 500 | `INTERNAL_ERROR`, generic message, no internals; full traceback logged with request id |

`X-Request-ID`: a caller-supplied value is reused only if it matches `^[A-Za-z0-9._-]{8,64}$`; otherwise a new 32-char hex id is generated. Present on every response, including 500s.

## Stage 1 — Foundation

Health probes are mounted at the root, outside `/api/v1`: they are infrastructure endpoints, not product API, and are not wrapped in the envelope.

| Method + path | Purpose | Access | Status |
|---|---|---|---|
| `GET /healthz` | Liveness; no dependency checks. `200 {"status":"ok"}` | Public | **Implemented** |
| `GET /readyz` | PostgreSQL + Redis answer within `READINESS_TIMEOUT_SECONDS` (default 2 s, checked concurrently). `200 {"status":"ok","checks":{"database":"ok","redis":"ok"}}`, or `503` with `"status":"unavailable"` and the failing check(s) marked `"unavailable"`. Reasons are logged, never returned | Public | **Implemented** |
| `GET /api/v1/openapi.json`, `GET /api/v1/docs` | OpenAPI schema, Swagger UI | Public, **disabled in production** | **Implemented** |

## Stage 2 — Auth and tenancy

Session cookie: `lf_session` (local/test) or `__Host-lf_session` (staging/production); HttpOnly, SameSite=Lax, Path=/, 30-day max age. Sessions also expire after 7 days without activity. Writes need `X-Requested-With: leadflow` (CSRF, see Conventions).

### Implemented (step 2.3)

| Method + path | Request body | Success | Errors | Limits |
|---|---|---|---|---|
| `POST /auth/signup` | `{email, password, full_name, business_name, timezone?}` (IANA zone, default `UTC`; unknown fields rejected) | `201`, `data: Me`, sets session cookie | `409 EMAIL_TAKEN`; `422 VALIDATION_ERROR`; `422 PASSWORD_POLICY` (details per rule) | 5 per hour per IP |
| `POST /auth/login` | `{email, password}` | `200`, `data: Me`, sets a new session cookie | `401 INVALID_CREDENTIALS` (identical for unknown email, wrong password, disabled account) | 5/min per IP+email; 30/min per IP |
| `POST /auth/logout` | — | `204`, session revoked server-side, cookie cleared. Idempotent | — | — |
| `GET /me` | — | `200`, `data: Me` | `401 UNAUTHENTICATED` | — |
| `PATCH /me` | `{full_name}` | `200`, `data: Me` | `401`, `422` | — |
| `POST /me/password` | `{current_password, new_password}` | `204`; **all** sessions revoked, a new cookie issued for this browser | `400 INCORRECT_CURRENT_PASSWORD`; `422 PASSWORD_POLICY` | 5 per 15 min per user |

`Me`:
```json
{ "user": { "id": "uuid", "email": "owner@example.com", "full_name": "Asha Verma",
            "email_verified": false, "created_at": "2026-11-12T18:20:39Z" },
  "memberships": [ { "tenant_id": "uuid", "tenant_name": "Acme Dental",
                     "tenant_slug": "acme-dental-6bd973", "role": "owner" } ] }
```
Passwords: 10–128 characters, not equal to the email. Emails are matched case-insensitively.

### Implemented (step 2.4): business and team

Every `/tenant…` route needs a session **and** `X-Tenant-ID: <business uuid>`. The header is checked against the caller's active membership before the handler runs.

| Situation | Response |
|---|---|
| Header missing | `400 TENANT_REQUIRED` |
| Header not a UUID | `400 INVALID_TENANT_ID` |
| Not a member, membership disabled, or business does not exist | `404 TENANT_NOT_FOUND` (identical in all three cases; logged and audited as `security.tenant_access_denied`) |
| Business suspended or cancelled | `403 TENANT_INACTIVE` |
| Role too low | `403 PERMISSION_DENIED` |

| Method + path | Body | Success | Errors | Who |
|---|---|---|---|---|
| `GET /tenant` | — | `200 data: Tenant` | — | any member |
| `PATCH /tenant` | any of `{name, timezone, locale}` (at least one; no nulls; unknown fields rejected) | `200 data: Tenant` | `422` | admin, owner |
| `GET /tenant/members` | — | `200 data: [Member]`, owners first, then admins, then agents, each by name | — | any member |
| `PATCH /tenant/members/{user_id}` | `{role: owner\|admin\|agent}` | `200 data: Member` | `404 MEMBER_NOT_FOUND`, `409 LAST_OWNER`, `422` | owner |
| `DELETE /tenant/members/{user_id}` | — | `204` | `404 MEMBER_NOT_FOUND`, `409 LAST_OWNER` | owner: anyone; admin: agents; anyone: themselves (leave) |

`Tenant`: `{id, name, slug, timezone, locale ("en", "en-IN", "en-GB"…), status, created_at}`.
`Member`: `{user_id, full_name, email, role, status, joined_at}`.

### Planned (step 2.5; see `STAGE_2_DESIGN.md` §8)

| Method + path | Purpose | Access |
|---|---|---|
| `POST /auth/password/forgot` · `POST /auth/password/reset` | Password reset by email | Public, rate limited · Reset token |
| `POST /auth/email/verify` · `POST /auth/email/verify/resend` | Email verification | Token · Session |
| `GET/POST /tenant/invitations` · `DELETE /tenant/invitations/{id}` | Invitations | Admin+ (verified email) |
| `GET /invitations/{token}` · `POST /invitations/accept` | Accept an invitation | Token |

## Stage 3 — CRM
| Method + path | Purpose | Access |
|---|---|---|
| `GET /contacts` · `POST /contacts` | List/search · create | Member · Agent+ |
| `GET /contacts/{id}` · `PATCH /contacts/{id}` | Detail · update | Member · Agent+ |
| `GET /leads` | Filter by status, priority, source, assignee, search; paginate | Member |
| `POST /leads` | Create lead (+ contact link) | Agent+ |
| `GET /leads/{id}` · `PATCH /leads/{id}` | Detail · update status/priority/assignee/fields | Member · Agent+ |
| `GET/POST /leads/{id}/notes` | Notes | Agent+ |
| `GET/POST /tasks` · `PATCH /tasks/{id}` | Follow-up tasks | Agent+ |
| `GET /dashboard/summary` | Counts by status/source, recent leads | Member |

## Stage 4 — Inbox
| Method + path | Purpose | Access |
|---|---|---|
| `GET /conversations` | Unified inbox (filter: channel, status, assignee, mode) | Member |
| `GET /conversations/{id}` | Detail | Member |
| `GET /conversations/{id}/messages` | History (cursor) | Member |
| `POST /conversations/{id}/reply` | Queue agent reply (`Idempotency-Key` header) | Agent+ |
| `POST /conversations/{id}/takeover` · `/release` | Switch handling mode human ↔ ai | Agent+ |
| `PATCH /conversations/{id}` | Status, assignee | Agent+ |
| `GET/POST /conversations/{id}/notes` | Internal notes | Agent+ |
| `POST /conversations/{id}/read` | Mark read | Member |
| `GET /events/stream` | SSE: new messages, status changes | Member |

## Stage 5 — Website widget
| Method + path | Purpose | Access |
|---|---|---|
| `POST /channels/website` · `PATCH /channels/{id}` | Create/configure widget channel | Admin+ |
| `GET /channels` | List channels and health | Member |
| `GET /widget/{public_key}/config` | Public config only | Public, origin allowlisted |
| `POST /widget/{public_key}/sessions` | Start/resume visitor session → signed visitor token | Public, rate limited |
| `POST /widget/messages` | Send visitor message (`client_message_id`) | Visitor token |
| `GET /widget/messages` · `GET /widget/stream` | History · SSE for replies | Visitor token |

## Stage 6 — AI
`GET/PUT /ai/settings`, `GET/POST/PATCH/DELETE /knowledge/faqs`, `POST /knowledge/sources` (upload), `GET /ai/usage` — Admin+.

## Stage 7 — Meta
| Method + path | Purpose | Access |
|---|---|---|
| `GET /channels/meta/connect` · `GET /channels/meta/callback` | OAuth onboarding | Admin+ |
| `DELETE /channels/{id}` | Disconnect | Admin+ |
| `GET /webhooks/meta` | Verification challenge | Provider verify token |
| `POST /webhooks/meta` | Receive events | `X-Hub-Signature-256` over raw body |
