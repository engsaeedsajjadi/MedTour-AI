# MedTour AI — Section 03: Technology stack, development verification

**2026-10-22 · Stage 03 · no real patient information permitted**

## Application integration and evidence

- Web client: Next.js 16 / TypeScript, existing independent TypeScript/audit/build CI.
- API: FastAPI / SQLAlchemy / Python 3.12; `/api/v1/health/live` reports process liveness, not dependency readiness.
- Database: PostgreSQL 17 with Alembic revision tracking. `/api/v1/health/ready` checks a tenant table, compares the PostgreSQL `alembic_version` against the actual repository Alembic head, and fails closed on mismatched migrations. SQLite is explicitly labeled `not_checked_sqlite` and allowed only for local/synthetic tests.
- Redis 7: readiness checks `REDIS_URL` when configured. Worker stores a short-lived heartbeat marker only, never patient content or credentials. Redis is not the durable message queue.
- Durable SQL outbox: existing `outbound_messages` records, approved generic templates and human approval. `send_one` uses row-lock + conditional update to claim status `approved -> sending` atomically across competing workers; a provider timeout or invalid response leaves `needs_reconciliation`, never automatically retried.
- Dedicated opt-in worker: `app.outbound_worker` polls a bounded batch, gated behind explicit `OUTBOUND_WORKER_ENABLED=true`, eligible WhatsApp provider credentials, `WHATSAPP_OUTBOUND_APPROVED=true` and explicit Docker `messaging` profile. The default Compose stack **does not** run this worker.
- Worker liveness: `app.worker_healthcheck` reads the Redis TTL heartbeat. No patient identifiers are written to Redis.
- S3/KMS/ClamAV: existing adapter remains blocked until separately approved/configured/tested.
- Production execution: intentionally blocked by section-02 `assert_safe_runtime()`, including the worker. Any deployment upgrade requires code review, rollout strategy, database principal separation, PostgreSQL RLS migration and independent medical/privacy/security approvals.

## Launching locally (synthetic testing only)

```sh
docker compose up -d --build db redis api web
docker compose ps
curl http://127.0.0.1:8000/api/v1/health/live
curl http://127.0.0.1:8000/api/v1/health/ready
```

Before enabling the optional worker in a controlled synthetic integration environment, satisfy ALL of the documented provider flags and configure credentials. Then:

```sh
docker compose --profile messaging up --build -d outbound-worker
docker compose --profile messaging ps
```

**Do not activate outbound provider messaging for real patients in this alpha release.** The command above does not itself establish Meta approval, patient consent, lawful cross-border processing or security sign-off.

## CI acceptance

1. `backend/tests/test_section_03_stack.py` checks configured/unconfigured readiness, migration validation, worker opt-in, bounded polling, at-most-one provider dispatch per approved outbox row in sequential synthetic tests, and manual reconciliation on timeouts.
2. Backend CI's `stack-integration` job runs real PostgreSQL 17 + Redis 7 containers, executes `alembic upgrade head` and verifies the `/health/ready` contract.
3. Existing backend synthetic tests and frontend CI must pass.
4. Real multiworker race/load testing, full tenant RLS migration, secure production DB principal separation, disaster recovery, runtime penetration testing, production-clinic approval and external provider E2E remain necessary.

**Section 03 verdict:** Local integration and software architecture improvements are testable. The Enterprise production technology stack is **not certified** until those outstanding requirements are addressed. Section 26 (RLS) and section 35 (production hardening) explicitly track the unresolved production dependencies.
