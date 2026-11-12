# Known Issues, Limitations and Pending Decisions

## Pending product-owner decisions

None open. Stage 2 decisions A–G were approved on 2026-11-12 (ADR-023).

Decisions D1–D10 from the Day 1 review were approved on 2026-11-12 (see "Resolved decisions").

## Resolved decisions (2026-11-12)

| # | Decision | Outcome |
|---|---|---|
| D1 | Git repository | `shahidk9626/aiMate` on GitHub. |
| D2 | Row Level Security from day one | Approved (ADR-006). |
| D3 | Authentication | Approved: short-lived access JWT + rotating refresh token in HttpOnly cookies, CSRF protection (ADR-004). |
| D4 | Tenant selection | Approved: `X-Tenant-ID` header verified against membership (ADR-005). |
| D5 | Real-time updates | Approved: Server-Sent Events (ADR-010). |
| D6 | Lead pipeline | Approved: fixed statuses + priority for MVP (ADR-011). |
| D7 | Runtime versions | Approved: Python 3.13, PostgreSQL 17, Node 22, SQLAlchemy 2.1. |
| D8 | Meta lead time | Approved: product owner starts the Meta developer app and business verification now. |
| D9 | Email provider | Approved in principle: one managed provider, chosen at Stage 2; mail catcher for local. **Provider name still to be chosen.** |
| D10 | Healthcare compliance | Approved: pilot with real estate, salons and agencies first; legal advice before selling to US healthcare. Data hosting region decided before first production deployment. |

## Open technical questions (resolved at the named stage)

- Stage 2: Postmark account, sending domain and DNS records (SPF/DKIM) are needed before emails can be sent outside local development.
- Stage 6: retrieval store (pgvector candidate), chunking, model choice and cost ceilings per plan.
- Stage 7: current Meta permission names, messaging-window rules, comment-to-DM limits — **not yet verified**; must be checked against current Meta documentation before design.
- Stage 9: billing provider(s) for INR vs USD/GBP.
- Before staging: domain name for app/API/widget hosts (cookies and CORS depend on a shared parent domain).

## Known limitations

- Python and Node dependency versions in `SETUP_GUIDE.md` were looked up, not installed; compatibility is confirmed as each step installs and tests them.
- Development environment only: anonymous pulls from Docker Hub were rate-limited (HTTP 429) in the cloud development container on 2026-11-12. The PostgreSQL image was pulled from Google's Docker Hub mirror (`mirror.gcr.io/library/postgres:17-alpine`, same official image) and tagged locally. This does not affect a developer machine or the VPS. If it recurs on a server, log in to Docker Hub or use the mirror.

- Development environment only: the cloud container sets a deprecated `UV_NATIVE_TLS` variable, so `uv` prints a warning. Harmless; unrelated to the project.

- Local docker only: the official PostgreSQL image makes `POSTGRES_USER` (`leadflow_owner`) a superuser. Superusers bypass RLS, which is why the app never connects as it. In production the owner must be a plain database owner, not a superuser — to be enforced in the deployment checklist (Stage 9).
- The role bootstrap sends the app password as an escaped SQL literal (DDL cannot take parameters). Do not run it while `log_statement = 'all'` is enabled on the server.
- `alembic upgrade head` runs migrations but does not run the bootstrap; on a brand-new environment run bootstrap first (the migration tolerates either order by creating the role `NOLOGIN` if missing).
- RLS scopes rows to the tenant id set for the transaction but does not itself verify the user's membership of that tenant (ADR-023, "Known limit"). Only the `tenant_context` dependency (step 2.4) and the token-validated signup and invitation flows may set it; code review must keep it that way.
- Downgrading migration `0002` keeps the `<app role>_lookup` role (like the app role), because roles are cluster-wide and may be used by another database.

- Rate limiting fails open when Redis is unreachable (logged as `rate_limit_unavailable`). Deliberate: failing closed would lock every user out during a Redis outage. Alert on that log event once monitoring exists (Stage 9).
- The web app's API client does not yet send `X-Requested-With: leadflow` on writes (it only makes GET requests so far); it must when the Stage 2 forms are built (step 2.6), or the API will answer `403 CSRF_REJECTED`.
- `TRUSTED_PROXY=cloudflare` must only be set when the API is reachable exclusively through Cloudflare (firewall the VPS to Cloudflare's IP ranges); otherwise clients could forge their IP in rate limits and audit logs.
- `WEB_ORIGIN` holds one origin. The website widget (Stage 5) is embedded on customer sites with their own origins and will use its own per-channel allowlist (`channels.allowed_origins`), not this setting.
- ESLint 9 is reported as deprecated by npm. We stay on 9 because `eslint-config-next` 16.4.6's plugins do not yet declare ESLint 10 support (ADR-021). Dev-only; not shipped.
- `NEXT_PUBLIC_API_URL` is fixed at build time; the same web build cannot be promoted between environments with different API URLs.
- `next dev` regenerates `apps/web/AGENTS.md` (Next.js agent notes). It is committed so the working tree stays clean.

- Development environment only: in the cloud development container, Docker builds need the environment's TLS-intercepting proxy and CA (`--network host`, proxy build args, `extra_ca` secret), and `ghcr.io` blob downloads are blocked. None of this applies on a normal machine or VPS. Because of it, `docker compose … --build` itself was not run there; the images were built with `docker build` from the same Dockerfiles and the stack was started with `--no-build`.
- The web image is ~413 MB, mostly the Node base image (~333 MB). Acceptable for now; a distroless or Alpine runtime can cut it later.
- Next.js's cache is per container (in memory + local disk). Fine for one web instance on a VPS; multiple instances would need a shared cache handler (see the Next.js self-hosting guide).

- Swagger UI (`/api/v1/docs`) cannot call write endpoints: it neither sends the CSRF header nor runs on `WEB_ORIGIN`. Use the curl examples in `SETUP_GUIDE.md`. Revisit if a developer-facing API is ever offered.
- Email verification and password reset are not available yet (step 2.5); until then a forgotten password cannot be recovered except by an operator.
- There is no "sign out all devices" or "active sessions" page yet; changing the password signs out all other sessions.
- Integration tests that simulate several browsers create one app instance per browser, because each TestClient runs its own event loop and an async connection pool must not cross loops. Production runs one loop per process, so this is test-only.

## Bugs

None.
