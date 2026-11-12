# API Contracts

**Status: PROPOSED. No endpoint is implemented yet.** Each endpoint is marked Implemented with its request/response schema when it ships. The generated OpenAPI document (`/api/v1/openapi.json`) becomes the machine-readable contract; TypeScript types in `packages/contracts` are generated from it.

## Conventions

- Base path `/api/v1`. JSON only. UTF-8.
- Auth: HttpOnly cookies (access + refresh). State-changing requests need header `X-Requested-With: leadflow` and a trusted `Origin`.
- Tenant: header `X-Tenant-ID: <uuid>` on every tenant-scoped route; verified against membership. Request bodies never contain `tenant_id`.
- Every response carries `X-Request-ID`.
- Pagination: cursor based — `?limit=50&cursor=<opaque>`.
- Roles: `agent < admin < owner`. "Agent+" means agent or higher.

Success:
```json
{ "data": { }, "meta": { "request_id": "…", "next_cursor": null } }
```

Error:
```json
{ "error": { "code": "LEAD_NOT_FOUND", "message": "Lead not found.", "details": [] },
  "meta": { "request_id": "…" } }
```

Cross-tenant access returns `404`, never `403`, so record existence is not revealed. Validation errors are `422` with field-level `details`. Rate limiting is `429` with `Retry-After`.

## Stage 1 — Foundation
| Method + path | Purpose | Access |
|---|---|---|
| `GET /healthz` | Liveness | Public |
| `GET /readyz` | DB + Redis reachable | Public |

## Stage 2 — Auth and tenancy
| Method + path | Purpose | Access |
|---|---|---|
| `POST /auth/register` | Create user + tenant + owner membership | Public, rate limited |
| `POST /auth/login` | Set session cookies | Public, rate limited |
| `POST /auth/refresh` | Rotate refresh token | Refresh cookie |
| `POST /auth/logout` | Revoke session, clear cookies | Authenticated |
| `POST /auth/password/forgot` | Send reset email (always 202) | Public, rate limited |
| `POST /auth/password/reset` | Set new password, revoke all sessions | Reset token |
| `GET /me` | User + memberships | Authenticated |
| `PATCH /me` | Update profile | Authenticated |
| `GET /tenant` · `PATCH /tenant` | Business profile and settings | Member · Admin+ |
| `GET /tenant/members` | List team | Member |
| `PATCH /tenant/members/{id}` · `DELETE …` | Change role / remove | Owner (admin for agents) |
| `POST /tenant/invitations` | Invite by email | Admin+ |
| `POST /invitations/accept` | Accept invite | Invite token |

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
