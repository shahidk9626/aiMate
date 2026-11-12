# Known Issues, Limitations and Pending Decisions

## Pending product-owner decisions

| # | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | **Git repository.** The workspace is not a git repository and the cloud session is temporary; files here are lost when it ends unless pushed. | Create a private GitHub repository and attach it to the session. | Stage 1 |
| D2 | **Approve ADR-003 … ADR-016** and the corrections I1–I15 / M1–M12 in `ARCHITECTURE_DECISIONS.md`. Most impactful: RLS from day one (ADR-006), cookie auth with rotating refresh (ADR-004), `X-Tenant-ID` tenant selection (ADR-005), SSE for real time (ADR-010). | Approve as proposed. | Stage 1–2 |
| D3 | **Lead pipeline.** Fixed statuses (`new, contacted, qualified, won, lost`) + priority, or per-tenant configurable stages in the MVP. | Fixed for MVP (ADR-011). | Stage 3 |
| D4 | **Runtime versions.** Python 3.13, PostgreSQL 17, Node 22 LTS, SQLAlchemy 2.1 (the brief says "2.0"; 2.1 is the current stable of the same 2.x API). | Approve. | Stage 1 |
| D5 | **Meta lead time.** App review and business verification can take weeks and gate Stage 7. | Product owner creates the Meta developer app and starts business verification now. | Stage 7 |
| D6 | **Transactional email provider** for password reset and invitations. | Pick one managed provider (e.g. Postmark, Resend or Amazon SES); local development uses a mail catcher container. | Stage 2 (reset/invite only) |
| D7 | **Compliance positioning.** US dental clinics and med spas are typically HIPAA-regulated; enquiries can contain health details that would be stored and sent to an LLM provider. UK GDPR and India's DPDP Act also apply to customer data. | For pilots: start with non-healthcare segments (real estate, salons, agencies) or India/UK clinics; scope US healthcare only after legal advice and provider agreements. Decide data hosting region before the first production deployment. | First pilot |
| D8 | **Domain name** for app/API/widget hosts (cookies and CORS depend on a shared parent domain). | Needed before staging deployment, not for local work. | Deployment |

## Open technical questions (resolved at the named stage)

- Stage 6: retrieval store (pgvector candidate), chunking, model choice and cost ceilings per plan.
- Stage 7: current Meta permission names, messaging-window rules, comment-to-DM limits — **not yet verified**; must be checked against current Meta documentation before design.
- Stage 9: billing provider(s) for INR vs USD/GBP.

## Known limitations

- HLD and LLD HTML are still v1.0 and contain the issues listed in `ARCHITECTURE_DECISIONS.md` Part 1. They will be revised to v1.1 after approval, not before.
- Dependency versions in `SETUP_GUIDE.md` were looked up, not installed; mutual compatibility is confirmed only when Stage 1 installs and tests them.

## Bugs

None (no code yet).
