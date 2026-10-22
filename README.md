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
