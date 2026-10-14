# MedTour AI — International Medical Tourism Coordination Platform

**Status: development foundation / NOT ready for real patient data.** This repository is an independent, original implementation inspired by the public interfaces/workflows of [HealthJourney](https://github.com/sartaj04/AI-Powered-Patient-Journey-Platform) (MIT), [Nile Care](https://github.com/YoumnKaram561/Nile-Care) (MIT), [Medplum](https://github.com/medplum/medplum) (Apache-2.0), and [Chatwoot](https://github.com/chatwoot/chatwoot) (mixed MIT / commercial Enterprise terms). **No source code from those repositories is copied or vendored.** They remain separate upstream integration/reference candidates; see [docs/UPSTREAM.md](docs/UPSTREAM.md).

Multilingual (fa/ar/en/ps/prs), WhatsApp-first international patient coordination for treatment in Iran. Built for privacy-aware human-supervised operations. **No provider has been connected, no live bookings or visa approvals are possible from this foundation.**

## Implemented now

- FastAPI API; tenant-scoped case, patient, hospital, physician, referral, appointment, quote, travel-request, task, consent and conversation records.
- Real persistence with SQLAlchemy. PostgreSQL recommended, SQLite only for isolated development/tests; explicit tenant filtering and access controls.
- Bearer JWT authentication with PBKDF2 passwords, configurable bootstrap admin, RBAC, tenant-scoped audit events.
- Patient case state transitions, approved quote workflow, referral review, manual/verified booking states, provider verification rules.
- Five-language structured intake prompts; consent-gated processing; deterministic emergency **keyword escalation (not medical triage)**.
- Secure document *metadata and upload-ticket* endpoint. Binary storage adapter not yet integrated: API refuses to claim the document was uploaded (fail-closed).
- Web chat conversation endpoints + human handoff and opt-in metadata. WhatsApp integration is blocked until official API eligibility is verified.
- Next.js responsive Persian RTL admin starter with functional CRUD views for core entities.
- Docker Compose (Postgres + API + Next.js), pytest API suite, GitHub Actions CI, environment templates.

## Quick start (development, non-PHI data ONLY)

```bash
cp .env.example .env
# Set a unique JWT_SECRET and BOOTSTRAP_ADMIN_PASSWORD in .env
# then:
docker compose up --build
# in another terminal:
docker compose exec api python -m app.bootstrap
```

UI: http://localhost:3000   |  API: http://localhost:8000/docs

Local backend without Docker:

```bash
cd backend
python -m venv .venv
# activate venv, then:
pip install -r requirements.txt
# SQLite is permitted only for development:
export DATABASE_URL=sqlite:///./medtour_dev.sqlite3
export JWT_SECRET='development-only-change-me-to-a-strong-random-secret'
export APP_ENV=development
python -m app.bootstrap  # requires BOOTSTRAP_ADMIN_PASSWORD, TENANT_SLUG, BOOTSTRAP_ADMIN_EMAIL
uvicorn app.main:app --reload
pytest -q
```

## Important safety boundaries

Do NOT use real patient data until privacy/legal/security review and a controlled production deployment are complete. The bootstrap account must never have a default password. Do NOT use the demo/local SQLite environment for actual health records. Physician verification is **not automated**; privileged users must review licenses. Patient medical decisions, travel fitness, appointments, prices, and visas **require verified humans/third parties**. There is no guarantee of WhatsApp/API eligibility for Iran; disabled integration is intentional.

## Repository guides

- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security and release gates](docs/SECURITY.md)
- [Upstream repositories and licenses](docs/UPSTREAM.md)
- [Roadmap to master prompt](docs/ROADMAP.md)
