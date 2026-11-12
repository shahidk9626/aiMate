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

- HLD and LLD HTML are still v1.0 and contain the issues listed in `ARCHITECTURE_DECISIONS.md` Part 1. Revision to v1.1 is Stage 1, step 5.
- Python and Node dependency versions in `SETUP_GUIDE.md` were looked up, not installed; compatibility is confirmed as each step installs and tests them.
- Development environment only: anonymous pulls from Docker Hub were rate-limited (HTTP 429) in the cloud development container on 2026-11-12. The PostgreSQL image was pulled from Google's Docker Hub mirror (`mirror.gcr.io/library/postgres:17-alpine`, same official image) and tagged locally. This does not affect a developer machine or the VPS. If it recurs on a server, log in to Docker Hub or use the mirror.

- `/healthz` requests are written to the access log. Fine locally; once uptime monitors poll it every few seconds this becomes noise. Revisit (sample or skip health paths) at Stage 1 step 5 / deployment.
- The API has no CORS, security headers, rate limiting or body-size limit yet. These arrive with the first endpoints that need them (Stage 2 auth) and are tracked there, not forgotten.
- Development environment only: the cloud container sets a deprecated `UV_NATIVE_TLS` variable, so `uv` prints a warning. Harmless; unrelated to the project.

## Bugs

None.
