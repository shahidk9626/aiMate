# Known Issues, Limitations and Pending Decisions

## Pending product-owner decisions

None open. Decisions D1–D10 from the Day 1 review were approved on 2026-11-12 (see "Resolved decisions").

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

- Stage 2: transactional email provider (Postmark, Resend or Amazon SES).
- Stage 6: retrieval store (pgvector candidate), chunking, model choice and cost ceilings per plan.
- Stage 7: current Meta permission names, messaging-window rules, comment-to-DM limits — **not yet verified**; must be checked against current Meta documentation before design.
- Stage 9: billing provider(s) for INR vs USD/GBP.
- Before staging: domain name for app/API/widget hosts (cookies and CORS depend on a shared parent domain).

## Known limitations

- Python and Node dependency versions in `SETUP_GUIDE.md` were looked up, not installed; compatibility is confirmed as each step installs and tests them.
- Development environment only: anonymous pulls from Docker Hub were rate-limited (HTTP 429) in the cloud development container on 2026-11-12. The PostgreSQL image was pulled from Google's Docker Hub mirror (`mirror.gcr.io/library/postgres:17-alpine`, same official image) and tagged locally. This does not affect a developer machine or the VPS. If it recurs on a server, log in to Docker Hub or use the mirror.

- The API has no security headers, rate limiting or body-size limit yet. These arrive with the first endpoints that need them (Stage 2 auth) and are tracked there, not forgotten. (CORS was added in Stage 1 step 4.)
- Development environment only: the cloud container sets a deprecated `UV_NATIVE_TLS` variable, so `uv` prints a warning. Harmless; unrelated to the project.

- Local docker only: the official PostgreSQL image makes `POSTGRES_USER` (`leadflow_owner`) a superuser. Superusers bypass RLS, which is why the app never connects as it. In production the owner must be a plain database owner, not a superuser — to be enforced in the deployment checklist (Stage 9).
- The role bootstrap sends the app password as an escaped SQL literal (DDL cannot take parameters). Do not run it while `log_statement = 'all'` is enabled on the server.
- `alembic upgrade head` runs migrations but does not run the bootstrap; on a brand-new environment run bootstrap first (the migration tolerates either order by creating the role `NOLOGIN` if missing).
- No tenant-owned tables exist yet, so RLS is proven on a test probe table only. Stage 2 must add `enable_tenant_rls_sql` to every tenant table migration and extend the isolation tests to real tables.

- Unhandled 500 errors are produced by Starlette's outermost error middleware, which sits outside CORS, so a browser sees them as `NETWORK_ERROR` rather than `INTERNAL_ERROR` (the response itself and the log are correct). Fix with a catch-all middleware inside CORS when the first real endpoints land (Stage 2).
- `WEB_ORIGIN` holds one origin. The website widget (Stage 5) is embedded on customer sites with their own origins and will use its own per-channel allowlist (`channels.allowed_origins`), not this setting.
- ESLint 9 is reported as deprecated by npm. We stay on 9 because `eslint-config-next` 16.4.6's plugins do not yet declare ESLint 10 support (ADR-021). Dev-only; not shipped.
- `NEXT_PUBLIC_API_URL` is fixed at build time; the same web build cannot be promoted between environments with different API URLs.
- `next dev` regenerates `apps/web/AGENTS.md` (Next.js agent notes). It is committed so the working tree stays clean.

- Development environment only: in the cloud development container, Docker builds need the environment's TLS-intercepting proxy and CA (`--network host`, proxy build args, `extra_ca` secret), and `ghcr.io` blob downloads are blocked. None of this applies on a normal machine or VPS. Because of it, `docker compose … --build` itself was not run there; the images were built with `docker build` from the same Dockerfiles and the stack was started with `--no-build`.
- The web image is ~413 MB, mostly the Node base image (~333 MB). Acceptable for now; a distroless or Alpine runtime can cut it later.
- Next.js's cache is per container (in memory + local disk). Fine for one web instance on a VPS; multiple instances would need a shared cache handler (see the Next.js self-hosting guide).

## Bugs

None.
