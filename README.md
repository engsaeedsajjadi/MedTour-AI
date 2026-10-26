# MedTour AI — Multilingual International Patient Coordination

**Version:** `0.5.0-alpha` · **Status:** expanded functional development build; **not production-ready** and **not a certified healthcare product**.

Patient-first medical tourism **coordination** system for international patients seeking care in Iran. Preferred channel: WhatsApp where the business and location are eligible; otherwise a private multilingual web portal and operator inbox. The system does **not** make diagnoses, prescribe care, issue visas, guarantee prices, or confirm reservations without independent human/provider verification.

> **Do not store real patient data or activate WhatsApp/outbound AI in this build.** Production rollout requires regulatory advice, credential verification, PostgreSQL RLS hardening, data-protection review, security testing, verified external providers and operational approvals.

## What works in the development build

- **Coordination core:** tenant-filtered accounts, JWT authentication, refresh rotation/replay blocking/logout, RBAC, patients, consents, medical cases, verified physician directory, hospitals, referrals, manually confirmed appointments, admin-approved quotations and line items.
- **Travel:** visa, hotels, transport, interpreter, diagnostic referrals and admission coordination as *manual* workflow requests; reference-required state transitions, history, lead attribution and agents.
- **Communication:** persisting staff/portal web messages, human handoff, five-language patient-facing **staged structured intake** and a human-reviewed AI translation draft workflow, safety-keyword escalation, optional approved-provider AI draft and translation adapter.
- **WhatsApp:** official Meta HMAC webhook validation, configured tenant/account matching, consent-based existing patient routing, idempotent receipt and quarantine of unknown contacts. **Disabled by default. New approved-template outbox + explicit send worker; no live outbound calls tested.** Eligibility and credentials remain an external prerequisite.
- **Telegram public onboarding (new, opt-in):** separate minimal ASGI gateway validates the official Telegram webhook secret, uses Redis replay fencing and sends non-clinical privacy notices in Persian, Arabic, English, Pashto and Dari. **Disabled by default; no patient/medical-text storage, no CRM intake, no AI and no verified live Telegram traffic.** Deployment steps in [docs/TELEGRAM_CHANNEL_MVP_FA.md](docs/TELEGRAM_CHANNEL_MVP_FA.md).
- **Files:** authenticated AES-GCM encrypted storage for **synthetic documents on development machines only**, and a gated S3 SSE-KMS + ClamAV adapter for production. Neither real S3 nor scanner was verified here. Patient portal now has an authorized multipart upload endpoint.
- **Patient-facing:** one-use purpose-specific patient consent links, revocable time-limited portal access links; journey status, approved quotes, confirmed appointments, controlled webchat.
- **Administration:** Persian RTL Next.js dashboard and CRUD/operations pages; approved CMS, approved knowledge base, price provenance, reports, service tracking, configurable safe tenant settings.
- **Finance:** deduplicated, admin-verified manual monetary records, **not payment collection or a regulated financial ledger**.
- **Verification:** **44 passing synthetic-data backend tests** (in the development environment), TypeScript syntax parsing for 31 source files. **Full Next.js dependency installation, typecheck and browser E2E were not completed in the current environment.**

## Case-centered mission coordination (Section 01)

A new staff-only `/journey` workspace and `GET /api/v1/cases/{case_id}/mission` show evidence-based administrative readiness. Case transitions block missing intake/referral/quote/appointment/travel/follow-up prerequisites, require supervisor references at high-stakes stages, and record scoped case timelines. See [Section 01 acceptance guide](docs/SECTION_01_ROLE_MISSION_FA.md). **This is synthetic-development coordination, not proof of real appointments, treatment, visa issuance or production readiness.**

## Section 02 safety principles (local)

The alpha API rejects `APP_ENV=production` until independently reviewed production security and regulatory gates are delivered. Consent withdrawal through staff or patient links cancels pending outbound templates, revokes portal access, and scrubs pending AI translation drafts; translation publication must re-check AI consent. External AI use requires an approved HTTPS host in `AI_APPROVED_HOSTS`. This does not certify clinical safety, professional approvals, or legal compliance. See [Section 02 report](docs/SECTION_02_NON_NEGOTIABLE_PRINCIPLES_FA.md).

## Section 03 — integrated development stack and opt-in worker

PostgreSQL/Alembic version and configured Redis are checked on API readiness; CI now tests real PostgreSQL 17 and Redis 7. A dedicated, disabled-by-default Docker `messaging` profile can consume the SQL-backed outbox once service-provider, customer-consent and operator approvals are configured. Claiming a message is atomic; unknown delivery outcomes are left for manual reconciliation and are not retried automatically. See [Section 03 architecture and runbook](docs/SECTION_03_TECH_STACK_FA.md). **No production PHI is permitted; PostgreSQL RLS production migration and external approvals remain open.**

## Section 04 — cross-module enterprise workspace

The staff dashboard now includes a tenant-scoped `/modules` workspace that links existing patient, case, intake, documents, physician, appointment, quote, travel and communication modules. The API provides a truthful module capability registry, case-level status aggregates and an audited administrative task lifecycle with no raw medical information in the read model. See [Section 04 scope](docs/SECTION_04_ENTERPRISE_MODULES_FA.md). **Specialist modules and external provider acceptance remain independently incomplete.**

## Section 05 — WhatsApp-first and safe alternatives

The staff `/messaging` interface now shows channel readiness without claiming a live connection; `/api/v1/channels` provides tenant-scoped options and a human-only secure-portal handoff. A separate `app.whatsapp_entrypoint:app` exposes only signed Meta verification/ingress, and signed delivery receipts update matching approved outbox statuses without auto retries. Existing Telegram is public-onboarding-only. See [Section 05 technical scope](docs/SECTION_05_CHANNELS_FA.md). **External provider authorizations, identity and security gates remain pending.**

## Section 06 — five-language administrative receptionist

A deterministic, non-diagnostic text receptionist now supports fa/ar/en/ps/prs administrative question routing, consented portal chat with explicit human handoff, Unicode-normalized precautionary urgency flags, five-language staff replies and a PHI-free `/receptionist` preview. No speech integration or verified translation/clinical approval is claimed; see [Section 06 report](docs/SECTION_06_MULTILINGUAL_RECEPTION_FA.md). The alpha remains unavailable for real patient information.

## Section 07 — medical intake administrative coordination

Shared patient/staff intake sessions, non-bypassable urgent warning state, renewed purpose-specific intake consent checks, audited request-more-information and admin handoff, and a PHI-minimized `/intake-review` staff queue are now implemented for development. This is **not clinical review or triage**. See [Section 07 scope and acceptance blockers](docs/SECTION_07_MEDICAL_INTAKE_FA.md).

## Section 07 continuation — clinician coordination metadata and urgent records

Staff can now record time-limited **locally attested** physician credential evidence, assign each reviewer to a specific submitted intake, track metadata-only non-diagnostic reviewer recommendations, and register emergency contact attempts without clearing the urgent flag. The `/intake-clinician` and `/intake-review` interfaces expose this administrative workflow. A new Alembic migration adds scoped audit tables. These controls **do not** independently verify licensure or authorize treatment, real patient data, emergency operation or production. See [Section 07 report](docs/SECTION_07_MEDICAL_INTAKE_FA.md).

## Section 08 — medical documents (synthetic development)

Tenant- and patient/case-scoped document uploads, lists and authenticated private downloads now enforce latest document consent; withdrawal permanently blocks previously uploaded blobs without falsely asserting physical erasure. Hardened AES-GCM test storage, metadata-only patient access records, S3/ClamAV readiness truthfulness and retention-review metadata APIs are documented in [Section 08](docs/SECTION_08_MEDICAL_DOCUMENTS_FA.md). **Real PHI, actual S3/KMS/ClamAV acceptance, legal retention processing, strong patient identity and production RLS are not certified.**

## Section 09 — Patient CRM (development only)

The `/crm` workspace integrates administrative case ownership, tenant-scoped follow-up scheduling, due queues, manually recorded outcomes and a human-only review of exact-contact duplicate candidates. Communication-consent withdrawal blocks pending follow-ups without reactivation on renewed consent. The `c9d093e78a21` migration and synthetic tests cover these workflows. No patient identities or medical data are automatically merged, and no external messages are sent. See [Section 09 scope](docs/SECTION_09_PATIENT_CRM_FA.md).

## Section 10 — administrative control center (development)

The administrator-only `/admin-center` provides tenant-scoped database metrics, a safety-prioritized and explicitly bounded operational action queue, redacted search across patients/cases/operations, non-clinical case snapshots and staff deactivation guarded by active assignments and audited identity controls. No automatic medical approval, data disclosure, messaging or live provider assertions are introduced. See [Section 10 scope](docs/SECTION_10_ADMIN_CONTROL_FA.md).

## Section 11 — Human Inbox (development)

Consent-bound staff claim/assignment and manual five-language webchat replies, safe status transitions, urgency metadata, patient-message reopening, restricted legacy routes and PHI-free audit are available in /conversations. Official Chatwoot/WhatsApp live integrations and production PHI authorization remain incomplete. See [Section 11](docs/SECTION_11_HUMAN_INBOX_FA.md).

## Section 12 — Physician management (synthetic development)

Tenant-safe physician-specific linked login, expiring *locally attested* credential records, hospital affiliations, proposed time slots and a restricted referral/appointment/availability portal are implemented for development testing. This does NOT independently certify any physician's license, hospital practice rights or appointment availability. See [Section 12](docs/SECTION_12_PHYSICIAN_MANAGEMENT_FA.md).

## Section 13 — hospital coordination (synthetic Alpha)

The admin `/hospital-management` and restricted `/hospital-workspace` now cover locally-attested hospital credential metadata, tenant-bound hospital staff accounts, service catalog, non-reservable proposed capacity and patient-consented, non-clinical case handoffs. Consent withdrawal permanently blocks outstanding coordination tasks. No external licence confirmation, live HIS booking or PHI transmission is enabled. See [Section 13](docs/SECTION_13_HOSPITAL_MANAGEMENT_FA.md).

## Section 14 — Provider matching (administrative only)

The `/provider-matching` screen and scoped API offer exact specialty directory options, evidence-gated proposals and an admin-reviewed nonclinical shortlist. No independent licensing, medical suitability determination, automatic referral or booking is claimed. See [Section 14](docs/SECTION_14_PROVIDER_MATCHING_FA.md).

## Section 15 — internal appointment calendar

The `/appointments` workspace now supports non-overlapping, timezone-aware internally proposed slots with administrator review, consent and tenant guard, and idempotency. These do not imply real hospital/physician booking. See [Section 15](docs/SECTION_15_APPOINTMENTS_FA.md).

## Section 16 — Versioned quotations (internal only)

Source-bound quote versions, reconciled financial totals, admin approval and export of approved internal PDF snapshots. Manual source-attested minor-unit FX ratios are supported without live FX. Multi-line UI, paginated English administrative PDF and approval revalidation added. No live FX, legal provider invoice, multilingual PDF or PHI production approval. See [Section 16](docs/SECTION_16_QUOTATIONS_FA.md).

## What is NOT finished

The 45-section enterprise master specification **has not yet reached full acceptance**. Critical remaining work includes PostgreSQL Row-Level Security and migration of existing pre-Alembic databases; full patient identity assurance and MFA; doctor/hospital independently scoped portals; real compliant WhatsApp outbound communication; five-language human-validated AI/voice; operational/independently verified S3/KMS storage and ClamAV scanning; approved external visa/hotel/provider APIs; payment gateways; subscription billing; load tests; frontend E2E and independent clinical/privacy/security review.

The complete section-by-section matrix is in **[docs/MASTER_45_TRACKER.md](docs/MASTER_45_TRACKER.md)**. No unfinished feature is represented as completed.

## Technology

| Area | Current technology |
|---|---|
| API | FastAPI / Python 3.12 / Pydantic |
| Web | Next.js 16 / React 19 / TypeScript |
| Database | PostgreSQL 17 (SQLite for synthetic tests only) |
| ORM | SQLAlchemy + Alembic baseline migration |
| Identity | PBKDF2, short access JWT, rotating 7-day refresh token |
| Encrypted *development* files | AES-256-GCM via `cryptography` |
| AI | disabled-until-approved OpenAI-compatible HTTP adapter |
| WhatsApp | disabled-until-approved official Meta webhook adapter |
| Infrastructure | Docker Compose, GitHub Actions backend/frontend CI |

This code was independently written with architecture patterns informed by public repositories: [HealthJourney (MIT)](https://github.com/sartaj04/AI-Powered-Patient-Journey-Platform), [Nile Care (MIT)](https://github.com/YoumnKaram561/Nile-Care), [Medplum (Apache 2.0)](https://github.com/medplum/medplum) and [Chatwoot (MIT core / separately licensed Enterprise)](https://github.com/chatwoot/chatwoot). **Their source code has not been merged into this package.** See [docs/UPSTREAM.md](docs/UPSTREAM.md).

## Development setup (synthetic test data only)

1. Make a copy of `.env.example` named `.env`.
2. Set `POSTGRES_PASSWORD`, update the password segment inside `DATABASE_URL` to match, and set **unique** `JWT_SECRET` (32+ characters) and `BOOTSTRAP_ADMIN_PASSWORD` (12+).
3. With Docker Desktop running:

```bash
docker compose up --build -d
docker compose ps
docker compose exec api python -m app.bootstrap
```

4. Log in at `http://localhost:3000/login`. OpenAPI at `http://localhost:8000/docs`.

No default admin password is bundled. Bootstrap refuses to overwrite existing users.

### Run the synthetic API tests

```bash
cd backend
python -m venv .venv
# Activate the venv, then:
pip install -r requirements.txt
python -m pytest -q
```

**Windows guide:** [docs/LOCAL_TEST_PLAN_FA.md](docs/LOCAL_TEST_PLAN_FA.md)

### Consent and portal access

An authenticated staff operator can issue purpose-specific patient consent links with `POST /api/v1/consent-links/{patient_id}/{purpose}`. In this development build, open `http://localhost:3000/consent#token=TOKEN` with synthetic identities; consent is one-time and expires after 30 minutes. Set a legally approved privacy notice and identity checks before live use.

### Portal access

After adding a patient, record explicit `communication` consent. In the authenticated OpenAPI interface use `POST /api/v1/portal/invites/{patient_id}`. Give the short-lived token privately to the **synthetic test patient**. Open `http://localhost:3000/patient-portal#access=TOKEN`; the fragment is removed from the address bar after ingestion.

### Secure files in development (optional)

The default upload response is `503`, by design. For synthetic files, set `ALLOW_DEV_ENCRYPTED_UPLOADS=true`, `PRIVATE_DOCUMENT_DIR` and a unique 32-byte URL-safe base64 `DOCUMENT_ENCRYPTION_KEY`. This is development-only, lacks active malware scanning and is **not approved for clinical records**. A separate production S3/KMS/ClamAV adapter is present but requires operator review, independent security testing and external infrastructure.

## New communication workflow

The admin menu now includes **پیام‌رسانی و ترجمه** (`/messaging`): approved generic WhatsApp templates are queued and reviewed, not sent automatically. `python -m app.delivery <outbound-id>` is an explicit optional delivery command and remains disabled until eligibility, approved templates and credentials exist. Translations require `communication` and `ai_processing` consent plus staff review and can only be published in the secure web chat.

## GitHub publication

Create an **empty private** repository named `MedTour-AI` under the account `engsaeedsajjadi` and run `./publish_github.ps1` from Windows PowerShell. The ZIP includes Git metadata with local commits for easy publishing. No GitHub repository has been created automatically by this package.

## Documentation

- [Next phase change report (Persian)](docs/NEXT_PHASE_REPORT_FA.md)
- [Master 45-section tracker](docs/MASTER_45_TRACKER.md)
- [Local tests](docs/LOCAL_TEST_PLAN_FA.md)
- [Release notes](docs/RELEASE_NOTES_2026_10_15.md)
- [Threats and security](docs/SECURITY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Verified upstream references](docs/UPSTREAM.md)

The platform remains a **development alpha** and must undergo local tests and independent production/security review before handling patients.

## Offline Telegram onboarding verification

```powershell
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -TelegramOnly
```

This test needs the existing local API Docker image, not a Meta account or Telegram token. No patient records are processed. **Never expose app.main to the internet merely for a Telegram webhook; deploy the isolated app.telegram_entrypoint:app behind HTTPS instead.**


Section 17 administrative visa coordination: see [docs/SECTION_17_VISA_FA.md](docs/SECTION_17_VISA_FA.md). No visa is issued or independently verified by this alpha platform.


Section 18 internal accommodation coordination: [docs/SECTION_18_ACCOMMODATION_FA.md](docs/SECTION_18_ACCOMMODATION_FA.md). Proposed local hotel inventory and reported external replies are NOT confirmed bookings.


Section 19: [Transport / interpreter coordination](docs/SECTION_19_TRANSPORT_INTERPRETERS_FA.md) is internal scheduling only, with no independently confirmed dispatch.


Section 20 international agent governance: [docs/SECTION_20_INTERNATIONAL_AGENTS_FA.md](docs/SECTION_20_INTERNATIONAL_AGENTS_FA.md). Account and contract review are internal only; external legal clearance and payouts disabled.


Section 21: [Development-only patient portal OTP invitation, consent and session security](docs/SECTION_21_PATIENT_PORTAL_FA.md). Real patient identity verification and production PHI remain disabled.


Section 22: [Five-language public website (FA/AR/EN/PS/PRS), draft templates, published-only SEO and legal readiness gates](docs/SECTION_22_MULTILINGUAL_WEBSITE_FA.md). Admin preview at /cms; public pages at /public/{tenant}/{locale}. Real legal notices, professional translations and clinical/partner verification remain external gates.


Section 23: [Tenant-scoped CMS versions, separate legal/medical/translation review roles, restored snapshot reapproval and migration disclosure](docs/SECTION_23_CMS_GOVERNANCE_FA.md). Governance workspace: /cms-workflow. Prior unreviewed published content is deliberately unpublished at migration.
