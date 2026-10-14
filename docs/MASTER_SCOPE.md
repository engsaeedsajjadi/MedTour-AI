# Original Enterprise master prompt coverage map

The original scope is broader than the verified foundation. This map prevents an unfinished module being misrepresented as delivered.

| Master prompt domain | Status | Planned acceptance gate |
| --- | --- | --- |
| Patient CRM and case tracking | Foundation implemented | Gate 1/2 |
| Identity, roles, multi-tenancy | Foundation implemented | Gate 1: RLS, MFA, user lifecycle |
| WhatsApp-first multilingual messaging | Signed webhook scaffold; channel disabled | Gate 3: approved Cloud API + durable processing |
| Conversational medical intake | Five languages and optional AI draft adapter | Gate 2: production AI evaluation and clinician approval |
| Medical document ingestion and OCR | Upload blocked until secure storage | Gate 2: encrypted private S3, scanning and audit |
| Human operator handoff | Basic conversation state available | Gate 3: full Chatwoot inbox bidirectional sync |
| Physician verification and referrals | Basic manual verification and referral | Gate 4: credentials + clinician portal |
| Hospital management | Provider directory with verification | Gate 4: partner contracts, hospital portal |
| Medical appointments | Requested and manual confirmed | Gate 4: verified calendar integration |
| Treatment pricing and quotations | Draft and manager approval | Gate 4: itemization, versions, FX, signed quote PDFs |
| Visa coordination | Request tracking only | Gate 4: manual/official external verification |
| Accommodation and transport | Request tracking only | Gate 4: real partners/booking references |
| Interpreter and home visit | Request tracking only | Gate 4: authorized providers and licensing |
| Patient portal and multilingual website | Planned | Gate 2 and 4 |
| International agents and referral tracking | Planned | Gate 5 |
| Invoices, payments and multi-currency accounting | Planned | Gate 4/5 |
| SaaS billing, plans and tenant settings | Planned | Gate 5 |
| Analytics, AI costs, alerts and audit | Basic dashboard + events | Gate 5 |
| Enterprise security, backup and recovery | Not accepted | Mandatory Gate 1 and Gate 5 |
| Production deployment, compliance and clinical review | Blocked | Gate 5 legal/technical sign-off |
