# Stage 2 Design — Authentication and Multi-Tenancy

**Status: APPROVED (2026-11-12) — decisions A–G accepted as recommended (ADR-023).** Step 2.1 is implemented; see `DEVELOPMENT_PROGRESS.md` for the current step.
Builds on: ADR-004 (auth), ADR-005 (tenant context), ADR-006 (RLS), ADR-007 (composite keys), ADR-020 (database roles).
Once approved, the decisions here become ADRs and this file stays as the stage's design reference.

---

## 1. Goal and exit criterion

A business owner can sign up, which creates their business. They can log in and out, reset a forgotten password, and invite teammates as admin or agent. A user who belongs to several businesses can switch between them.

**Exit criterion:** two businesses use the app at the same time. Automated tests prove that neither can read or change the other's data, at the API level and at the database level.

Out of scope: social login, two-factor authentication, SSO, billing, deleting a business, transferring ownership. All are noted for later.

---

## 2. Decisions that need your approval

| # | Decision | Recommendation | Why |
|---|---|---|---|
| **A** | Login session mechanism | **Opaque server-side sessions** (changes ADR-004) | See §4. Same security, less moving parts, instant logout, one dependency fewer |
| **B** | Transactional email provider | **Postmark** (Resend and Amazon SES are fine alternatives) | All three support SMTP, which is the only thing our code will use, so switching later is a settings change. Postmark only does transactional email. SES is cheapest at volume but needs more setup (sandbox exit, DNS). **Please check current pricing and sender support for India/UK/US before choosing.** |
| **C** | Email verification | **Sent at signup, not required to log in; required before inviting teammates** (and later before connecting channels) | Keeps signup friction low for demos while stopping unverified accounts from emailing other people |
| **D** | "Email already registered" on signup | **Say so (409), with strict rate limiting** | The alternative ("check your email" for everyone) hides whether an account exists but forces an email round-trip before anyone can try the product. Login and password reset never reveal account existence |
| **E** | Password rules | **10–128 characters, no forced symbols/digits, not equal to the email** | Current NIST guidance (SP 800-63B): length beats composition rules. Checking against known-breached passwords can be added later |
| **F** | Page protection in the web app | **In the browser** (the app asks the API "who am I?" and redirects to login on 401) | The session cookie belongs to the API's domain, so the Next.js server cannot see it. Real protection is the API itself; the browser check is only for user experience |
| **G** | Pre-tenant lookups under RLS | **Small `SECURITY DEFINER` database functions** (refines ADR-006) | See §5.3. Narrower than the "system session that bypasses RLS" ADR-006 suggested |

---

## 3. Data model — migration `0002`

All tables follow `DATABASE_SCHEMA.md` conventions (UUIDv7, timestamps, VARCHAR + CHECK). Changes from the approved schema are marked **new**.

| Table | Scope | Notes |
|---|---|---|
| `users` | global | email CITEXT unique, Argon2id hash, `email_verified_at`, `is_platform_admin` |
| `tenants` | RLS (special policy, §5.2) | name, slug (unique), timezone, locale, status, settings |
| `memberships` | RLS (special policy, §5.2) | `UNIQUE(tenant_id, user_id)`, role owner/admin/agent, status |
| `auth_sessions` | global, auth service only | **Changed for decision A:** `token_hash` unique, `user_id`, `created_at`, `last_seen_at`, `expires_at` (absolute), `revoked_at`, `user_agent`, `ip`. No `family_id` (no refresh-token rotation needed) |
| `email_tokens` | global | **new:** replaces `password_reset_tokens`; one table for password reset and email verification: `purpose`, `token_hash` unique, `user_id`, `expires_at`, `used_at` |
| `invitations` | RLS | `token_hash` unique, email, role, `invited_by`, `expires_at`, `accepted_at`, `revoked_at`; one pending invite per (tenant, email) |
| `audit_logs` | RLS (special policy) | append-only: app role gets `INSERT, SELECT` only |
| `outbox_events` | global | needed now to send emails reliably (§7) |

**Tenant mixin** (code): adds `tenant_id`, `UNIQUE(tenant_id, id)`, and the RLS policy through `enable_tenant_rls_sql()`, so every later tenant table gets isolation by default.

**Invariant enforced in the service layer and tested:** a business always has at least one active owner.

---

## 4. Sessions (decision A)

**Approved Day 1 design (ADR-004):** a 15-minute JWT access token plus a rotating refresh token. Logging out or removing a member only takes effect when the access token expires, unless every request also checks the database. If every request checks the database anyway, the JWT adds signing-key management and a second token but no benefit.

**Proposed:** one opaque session token.

- **Token:** 256-bit random value sent as a cookie. The database stores only its SHA-256 hash. Every request does one indexed lookup, which is cheap, and we already open a transaction per request.
- **Lifetime:** expires after 7 days without use, and 30 days after login regardless of use. `last_seen_at` is updated at most every 5 minutes.
- **Revocation:** logout deletes that session. Password reset and password change revoke all of the user's sessions. Removing a member takes effect on their next request, because tenant membership is re-checked on every request.
- **Rotation:** a new token is issued at login and after a password change, which prevents session fixation.
- **Cookie:**
  - Production: `__Host-lf_session`.
  - Local development: `lf_session` (`__Host-` requires HTTPS).
  - Attributes: `HttpOnly`, `Secure` (production), `SameSite=Lax`, `Path=/`, no `Domain`.
- **Future mobile app:** the same token can be sent as `Authorization: Bearer`. Nothing in the design blocks that.
- **Dependencies:** `pyjwt` is no longer needed. `argon2-cffi` is still needed.

If you prefer to keep ADR-004 as approved, the rest of this design is unchanged: the session table gains a refresh-token family and the API adds token signing.

---

## 5. Tenant context, RBAC and RLS

### 5.1 Request flow
1. `current_user` dependency: reads the session cookie, looks up the session, loads the user, rejects inactive users (401), and sets `app.user_id` for the transaction.
2. `tenant_context` dependency (tenant routes only):
   - Reads `X-Tenant-ID`. It must be a UUID, otherwise 400.
   - Loads the active membership for that user and tenant. If there is none, it returns 404 (never 403, so existence isn't revealed) and logs a security event.
   - Sets `app.tenant_id` and returns `TenantContext(tenant_id, user_id, role)`.
3. **Services** receive the `TenantContext`. Permission checks live in services (`ctx.require(Role.ADMIN)`), not in route handlers or the frontend.

### 5.2 RLS policies (database level)
| Table | Policy |
|---|---|
| Standard tenant tables (`invitations`, and every future CRM/inbox table) | `tenant_id = current tenant` (the shipped Stage 1 policy) |
| `memberships` | read: `tenant_id = current tenant OR user_id = current user` (so "which businesses am I in?" works); write: `tenant_id = current tenant` |
| `tenants` | read: `id = current tenant OR the current user has a membership in it`; write: `id = current tenant` |
| `audit_logs` | read: `tenant_id = current tenant`; insert: `tenant_id IS NULL OR tenant_id = current tenant`; no update/delete grants |

### 5.3 Lookups before the tenant is known (decision G)

> Implemented in step 2.1 with a dedicated NOLOGIN lookup role owning the functions. A function owned by the owner role would see nothing under FORCE RLS on a non-superuser production database. RLS was also extended to `users`, `auth_sessions` and `email_tokens`. See ADR-023 and `DATABASE_SCHEMA.md`.

Some flows must find a row before any tenant context exists: accepting an invitation by its token, and later resolving a widget key or a Meta page id to its channel. These go through small `SECURITY DEFINER` functions owned by the owner role. Each one:
- takes the token hash and returns **only ids** (e.g. `tenant_id`, `invitation_id`);
- after that, the service sets the tenant context and reads the full row normally, under RLS.

There is no general-purpose "bypass RLS" connection anywhere in the app.

### 5.4 Role matrix (Stage 2 actions)
| Action | Owner | Admin | Agent |
|---|---|---|---|
| View business profile, team list | ✓ | ✓ | ✓ |
| Edit business profile / settings | ✓ | ✓ | — |
| Invite / remove / change role of **agents** | ✓ | ✓ | — |
| Invite / remove / change role of **admins and owners** | ✓ | — | — |
| Remove or demote the last owner | — | — | — |
| Leave a business (if not the last owner) | ✓ | ✓ | ✓ |

---

## 6. Security controls added in Stage 2

| Control | Design |
|---|---|
| Password hashing | Argon2id via `argon2-cffi` defaults (RFC 9106 profile); transparent rehash on login if parameters change; dummy hash on unknown email so timing does not reveal accounts |
| CSRF | `SameSite=Lax` cookie **plus** required `X-Requested-With: leadflow` header on POST/PUT/PATCH/DELETE **plus** `Origin` must equal `WEB_ORIGIN`. The custom header forces a CORS preflight that only the trusted origin passes |
| Rate limiting | Redis counters (small in-house helper, no new package). Login: 5/min per IP+email and 30/min per IP. Signup: 5/hour per IP. Password reset: 3/hour per email and 10/hour per IP. Invitations: 50/day per business. No account lockout (lockouts let attackers block real users) |
| Client IP | Direct peer address locally. Behind Cloudflare, `CF-Connecting-IP` only when `TRUSTED_PROXY=cloudflare` is set |
| Security headers (API) | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Cache-Control: no-store` on auth/me responses; HSTS at Cloudflare in production |
| Security headers (web) | Same basics via `next.config` headers; full Content-Security-Policy in Stage 5 (when the widget defines embedding rules) |
| Request size | 1 MB default body limit (413) |
| Errors | Fix from `KNOWN_ISSUES.md`: unhandled errors return the JSON envelope **with CORS headers** |
| Audit | `auth.signup`, `auth.login`, `auth.login_failed` (no email stored, only user id if known), `auth.logout`, `auth.password_reset_requested/completed`, `member.invited/joined/role_changed/removed`, `tenant.updated` |
| Logging | Never log passwords, tokens, cookies, or email addresses; user and tenant ids only |

---

## 7. Email (decision B)

- **One interface:** `send_email(to, template, data)`, called only from a Celery task. The message is first written to `outbox_events` in the same transaction as the business change, so a crash cannot lose a password-reset email, and email is never sent while a request is waiting.
- **Transport:** SMTP via Python's standard library, so no new package. Provider credentials come from environment variables.
- **Local development:** a **Mailpit** container in compose captures every email, viewable at http://localhost:8025. Nothing leaves your machine.
- **Templates:** password reset, email verification, invitation. Plain text + simple HTML, no tracking pixels.
- **Celery** (`celery` 5.7, already chosen in the HLD) arrives in this stage: a `worker` service plus an outbox relay task.

---

## 8. API (new endpoints)

All under `/api/v1`. Error format and conventions as in `API_CONTRACTS.md`. "Tenant" means `X-Tenant-ID` is required.

| Method + path | Body → result | Access |
|---|---|---|
| `POST /auth/signup` | `{email, password, full_name, business_name, timezone?}` → 201 user + tenant; session cookie set | Public, rate limited |
| `POST /auth/login` | `{email, password}` → 200 user + memberships; session cookie set. Wrong email or password → 401 `INVALID_CREDENTIALS` (same message for both) | Public, rate limited |
| `POST /auth/logout` | → 204; session revoked, cookie cleared | Session |
| `POST /auth/password/forgot` | `{email}` → always 202 | Public, rate limited |
| `POST /auth/password/reset` | `{token, new_password}` → 204; all sessions revoked | Token |
| `POST /auth/email/verify` | `{token}` → 204 | Token |
| `POST /auth/email/verify/resend` | → 202 | Session, rate limited |
| `GET /me` | → user + memberships (tenant id, name, role) | Session |
| `PATCH /me` | `{full_name}` → user | Session |
| `POST /me/password` | `{current_password, new_password}` → 204; other sessions revoked | Session |
| `GET /tenant` · `PATCH /tenant` | business profile and settings | Tenant member · Admin+ |
| `GET /tenant/members` | team list | Tenant member |
| `PATCH /tenant/members/{user_id}` | `{role}` | Per role matrix |
| `DELETE /tenant/members/{user_id}` | remove (or leave, if self) | Per role matrix |
| `GET /tenant/invitations` · `POST` · `DELETE /{id}` | list, invite `{email, role}`, revoke | Admin+ (verified email) |
| `GET /invitations/{token}` | → business name, role, inviter name, whether an account exists | Token |
| `POST /invitations/accept` | `{token}` if logged in with that email; or `{token, password, full_name}` to create the account | Token |

---

## 9. Web app (Stage 2 pages)

| Route | Purpose |
|---|---|
| `/signup` | Business name, your name, email, password |
| `/login` | Email, password; link to reset |
| `/forgot-password`, `/reset-password?token=…` | Reset flow |
| `/verify-email?token=…` | Confirms email |
| `/invite?token=…` | Accept invitation (log in or create account) |
| `/app` | Signed-in home: welcome, empty states for CRM/inbox ("coming in Stage 3/4"), verification banner |
| `/app/settings/business` | Business profile (admin+) |
| `/app/settings/team` | Members, roles, invitations (per role matrix) |
| Header | Workspace switcher (stored per browser), profile menu, logout |

The API client sends `X-Requested-With: leadflow` on write requests and `X-Tenant-ID` when a business is selected. A shared auth layer under `/app` calls `GET /me`. On 401 it redirects to `/login?next=…`, accepting only same-site paths so the redirect can't be abused.

---

## 10. Tests that must pass before Stage 2 is signed off

- **Isolation:**
  - With two businesses and three users (one belonging to both), every tenant endpoint returns 404 for a business the user isn't in.
  - Database-level RLS tests on the real `tenants`, `memberships`, `invitations` and `audit_logs` tables.
- **Authentication:**
  - Signup, login, me and logout end to end.
  - Expired, revoked and tampered tokens are rejected.
  - Password reset revokes all sessions.
  - The unknown-email and wrong-password responses are identical.
- **Roles:** every cell of the role matrix, including the last-owner rule.
- **Security:**
  - Writes without the CSRF header or with a foreign `Origin` are rejected.
  - Rate limits trigger.
  - Cookie flags are correct in each environment.
  - Body limit and security headers are present.
  - A 500 response carries CORS headers.
- **Email:** outbox to worker to Mailpit, in an integration test; reset and invite links work.
- **Web:** form validation, auth redirects, workspace switching. One browser end-to-end run: signup, invite, accept as a second user, switch business, logout.

---

## 11. Implementation steps (each reviewed before the next)

| Step | Scope |
|---|---|
| 2.1 | Migration `0002`: tables, tenant mixin, RLS policies, definer functions; database isolation tests |
| 2.2 | Security plumbing: password hashing, session tokens, rate limiter, CSRF/Origin check, security headers, body limit, 500-with-CORS fix |
| 2.3 | Auth endpoints: signup, login, logout, me, profile, change password |
| 2.4 | Tenant context, RBAC, business and team endpoints, audit log |
| 2.5 | Outbox, Celery worker, Mailpit, email sending; password reset, email verification, invitations |
| 2.6 | Web: auth pages, `/app` shell, workspace switcher, settings pages |
| 2.7 | End-to-end check, docs, Stage 2 sign-off |

New dependencies, each explained again at its step: `argon2-cffi` (2.2), `celery` (2.5). No new web packages are planned.
