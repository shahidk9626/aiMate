# AI LeadFlow — Project Context

> Read this file first in any new session, then `DEVELOPMENT_PROGRESS.md` for where we are.
> Architecture source of truth: `AI-LeadFlow-HLD.html`, `AI-LeadFlow-LLD.html` (v1.1, 2026-11-12), with the decision log in `ARCHITECTURE_DECISIONS.md`. When they disagree, the newer decision record wins and the HTML is updated.

## 1. What we are building

A commercial, multi-tenant SaaS: **AI-powered enquiry automation + unified CRM** (comparable to DM Champ).

Promise: *"Never miss a customer enquiry again. Let AI respond, qualify, organize and route your leads automatically."*

Businesses receive enquiries on Instagram DMs/comments, Facebook Messenger and their website. Today they answer manually, late, and lose leads. AI LeadFlow pulls every enquiry into one workspace, lets a business-specific AI agent hold the first sales conversation, qualifies the lead, and hands over to a human when needed.

- Markets: India, USA, UK.
- Segments: dental clinics, real estate agencies, med spas, salons, digital marketing agencies, other enquiry-driven businesses.
- Revenue: monthly subscription + one-time onboarding fee + AI customization; agency/white-label later.
- Go-to-market: working demo → personalized demos → 2–3 pilot clients → measure response time / lead capture / appointments → testimonials → scale. Never promise an integration that is not working.

## 2. Core workflow (same for every channel)

1. Inbound message arrives (widget request or signed provider webhook).
2. Verify, deduplicate, persist durably, acknowledge fast.
3. Resolve channel → tenant; find or create contact; find or create conversation; find or create lead.
4. Worker builds tenant-only context: approved knowledge, conversation history, agent policy.
5. LLM returns a **structured** result: reply text, extracted lead fields, proposed typed actions, confidence.
6. Backend validates output and actions; low confidence / complaint / sensitive / explicit request → human handoff.
7. Outbound message is persisted as queued, sent via the channel adapter, delivery result recorded.
8. Lead qualification, status and priority updated; team notified. A human can take over at any time, which silences the AI on that conversation.

Hard rule: the AI never invents prices, offers, availability or promises. If knowledge is missing it asks or hands off.

## 3. Product modules

A. Auth (signup, login, logout, password reset, sessions, profile)
B. Multi-tenant business management (onboarding, profile, settings, Owner/Admin/Agent, strict isolation)
C. Unified CRM (dashboard, leads, contacts, source, status, priority, assignment, search, pipeline, notes, tasks)
D. Unified inbox (all channels, history, takeover, assignment, internal notes, status)
E. AI agent engine (knowledge base, FAQs, hours, context, qualification, structured extraction, confidence, handoff, usage tracking)
F. Channels — initial: website chat, Instagram messaging, Facebook Messenger. Future: WhatsApp.
G. Website chat widget (embeddable JS, per-business config, persistence)
H. Automation engine (triggers, assignment, notifications, reminders, rules)
I. Analytics
J. SaaS billing (plans, usage limits, trials, payments)
K. Platform administration

## 4. Technical stack (final — do not change without discussion)

| Layer | Choice |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy 2.x |
| Database | PostgreSQL, Alembic migrations |
| Background | Redis + Celery (separate worker process) |
| AI | OpenAI API behind a provider-independent abstraction |
| Integrations | Meta Graph API, Instagram Messaging API, Messenger Platform |
| Infra | Docker, Docker Compose, Cloudflare, VPS |
| Testing | Pytest, backend integration tests, frontend tests, API contract tests |

**NestJS and Drizzle were dropped. Never generate NestJS or Drizzle code.**

Shape: modular monolith + separate worker. No microservices.

## 5. Non-negotiables

- Tenant isolation on every query and mutation; never trust a client-supplied tenant id without membership verification; PostgreSQL RLS as defense in depth.
- Argon2id passwords, secure sessions, RBAC in the service layer.
- Encrypted channel credentials; webhook signature verification on the raw body; idempotent ingestion.
- Rate limiting, input validation, audit logging, safe errors, no secrets in Git or frontend, no customer PII in logs.
- AI: customer messages and uploaded documents are untrusted data; tenant-only knowledge; LLM proposes typed actions, backend validates; no arbitrary SQL or backend operations.

## 6. Delivery stages

1. Foundation (monorepo, Next.js, FastAPI, Postgres, SQLAlchemy, Alembic, Docker, config, logging, health)
2. Auth + multi-tenancy
3. CRM
4. Unified inbox
5. Website enquiry integration (widget)
6. AI engine
7. Instagram + Facebook (verify current Meta requirements first)
8. Automation + analytics
9. Commercial launch (plans, billing, onboarding, production, monitoring)

WhatsApp is a future phase.

## 7. Working rules

One milestone at a time. Explain purpose, architecture and files before coding. Small steps, run tests, fix before moving on. Inspect before modifying; never overwrite blindly. Explain every new dependency. Business logic out of route handlers. Never hardcode credentials or fake an integration. Never skip security. Wait for product-owner approval between milestones. Update the docs in this folder at the end of every milestone.

## 8. Documentation map

| File | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | This file |
| `ARCHITECTURE_DECISIONS.md` | Decisions, alternatives, reasons, approval status |
| `DEVELOPMENT_PROGRESS.md` | Milestones done, current, exact next task |
| `DATABASE_SCHEMA.md` | Tables, relationships, constraints, indexes |
| `API_CONTRACTS.md` | Endpoints, payloads, envelope, errors |
| `SETUP_GUIDE.md` | Tooling, env vars, local run |
| `KNOWN_ISSUES.md` | Bugs, limitations, pending decisions |
