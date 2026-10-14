# Completion roadmap relative to Enterprise Master Prompt

## Gate 1 — Core integrity

- Replace `create_all` with Alembic migrations and enforce PostgreSQL RLS.
- Build user invitation management, MFA, token rotation/revocation, patient identity and scoped record permissions.
- Add full consent collection and revocation rules, CSRF/CSP policy, immutable audit and multi-tenant tests.
- Verify frontend build, accessibility and complete core CRUD.

## Gate 2 — Secure patient onboarding

- Private encrypted object storage, file virus scanning, role-bound download, FHIR data mapping.
- Patient portal with secure identity and authorized representative consent.
- AI provider adapter with compliant deployment option, structured multi-language intake and tested fallbacks.
- Five-language localization of actual UI, verified high-quality Pashto and Dari translations, clinician escalation rules.

## Gate 3 — Omnichannel operations

- Chatwoot API and signed webhook adapter, message routing, inbound/outbound flow and escalation synchronization.
- WhatsApp adapter only after official business/API eligibility and country restrictions are cleared.
- Respect privacy, WhatsApp 24-hour window/approved template and patient opt-in.

## Gate 4 — Provider network and travel

- Physician/hospital credential audit, secure portals, full referral and appointment calendars.
- Versioned itemized approved quotes, FX source, payment reconciliation.
- Partner API/manual-confirmation workflows for visa assistance, hotels, transport, translators, and home visits.
- External international representative portal, CRM conversion funnel and performance analytics.

## Gate 5 — Enterprise launch

- Multi-organization billing and quotas, white labels, tenant-specific policies, telemetry and operations handbook.
- End-to-end tests of WhatsApp/web chat to human decision to treatment travel, pentesting and load testing.
- Legal/clinical review, operator training, live pilot approval, change control and post-treatment follow-up.

### GitHub publication

GitHub's connected API tools available in this environment cannot create a repository. Once the owner creates a **private empty repository** at `https://github.com/new`, publishing the local repository is simply:

```bash
git remote add origin https://github.com/engsaeedsajjadi/MedTour-AI.git
git push -u origin main
```

Confirm the repository's exact name and owner before copying these commands. Preserve it as private until the software and legal/privacy posture are reviewed.
