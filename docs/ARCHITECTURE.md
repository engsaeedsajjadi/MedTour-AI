# Architecture — current vs target

## Current implemented foundation

```
Next.js admin (browser) --> FastAPI /api/v1 --> SQLAlchemy --> PostgreSQL
                                       |
                                       +--> JWT / role guards / tenant filters
                                       +--> Audit events
                                       +--> Non-diagnostic 5-language intake text routing
                                       +--> Manual physician/quote/travel workflows
```

Login uses bearer JWT, tenant scoped subject. All current read/write APIs explicitly restrict by token tenant ID; IDs provided by caller are separately checked. Admin/coordinator-only endpoints prevent a patient from reading other records. `app.initialize` and `app.bootstrap` run only in development; production needs fully reviewed migrations and RLS.

## Target after hardening

```
WhatsApp Cloud API (eligible businesses only) --\
Web patient portal ----------------------------+--> Channel Gateway --> Chatwoot operator inbox
Email -----------------------------------------/             |
                                                             v
                                                   Intake Orchestrator
                                                  /       |         \
                                          Consent   AI gateway   Human handoff
                                                            |
FastAPI API --> Tenant-aware services --> Postgres + RLS     |
        |                        |                           |
      Workers              Private S3 + AV scanning      Clinician signoff
        |
Doctor/Hospital verification + quotations + bookings + visa/hotel/transport orchestration
```

Future integration must adapt upstream technologies through stable APIs: Chatwoot is a distinct application; Medplum may be a clinical FHIR system, not a second uncoordinated copy of patient data. Every event needs idempotency keys, durable queue handling, audit records, legal/medical human approvals and business continuity without WhatsApp.

## Data boundaries

- No direct LLM access to private files until consent and DPA approvals.
- No automatic clinical diagnosis, triage or travel fitness decisions.
- No auto-confirmation of appointments or visa issuance.
- No production PHI until security, consent, retention, legal and deployment gates pass.
- HealthJourney and Nile Care are references, not yet part of the deployed runtime.
