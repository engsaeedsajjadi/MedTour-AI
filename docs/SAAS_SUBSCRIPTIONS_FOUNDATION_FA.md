# MedTour AI — SaaS quota foundation (development only)

Updated: 2026-10-22. Branch: `enterprise/complete-gaps-2026-10-22`.

This phase implements **technical provisioning and resource guards**, not payments,
subscription commerce or production authorization. Never use it to handle real patients.

## Delivered API and dashboard

- `GET /api/v1/saas/plans`: authenticated admin-only technical catalogue
  (FREE, STARTER, GROWTH, ENTERPRISE), without commercial prices.
- `GET /api/v1/saas/subscription`: tenant-specific status. No cross-tenant lookup.
- `POST /api/v1/saas/subscription/activate-free`: **one-time**, audited
  tenant FREE activation by an existing admin. No paid plan activation.
- `GET /api/v1/saas/usage`: DB-derived live counts of patients, cases and staff
  with tenant filtering and corresponding plan limits.
- Persian `/saas` dashboard for admin operators.
- `POST /patients`, `POST /cases`, and `POST /staff` now call
  `enforce_create_quota` before inserting the new row, in the same transaction.

## Storage and concurrency

Migration `831ed6424f1c` adds one `tenant_subscriptions` record per tenant.
The table uses the tenant ID as its primary key, with a foreign key to
the provisioning user and no payment credentials.

Quota checks acquire a PostgreSQL `SELECT ... FOR UPDATE` lock on the owning
tenant row. The count and protected creation must share the same DB
transaction. This serializes **these three creation endpoints** across API
workers when all workers write through the PostgreSQL primary. It does not
protect imports, other write routes, replica reads, or unreviewed direct
SQL writers; those require independent acceptance.

Existing alpha development tenants are **not automatically enrolled** and
retain legacy behavior until they activate a subscription. In
`APP_ENV=production`, all three creation routes deny unprovisioned tenants
instead of granting implicit unlimited capacity. This is not a substitute
for completing the production tenant pool/RLS migration.

## Important incomplete work

1. Pricing, tax, invoicing, currency, contracts, subscriptions lifecycle,
   payment provider verification/webhooks and reconciliation.
2. A trusted provider-controlled paid-plan activation and downgrade path;
   admin cannot claim that payment occurred via this API.
3. Usage caps for AI tokens, messages, voice minutes, storage and worker jobs.
4. Tenant-specific external billing accounts, metering ledger, alerts and
   monthly rollover with idempotent event ingestion.
5. Full tenant PostgreSQL RLS in live runtime, strong staff MFA,
   independent threat modeling, real PostgreSQL concurrency tests and
   audited production migrations.
6. Expired/suspended plan controls are in the internal schema, but no
   billing worker or scheduled renewal transitions are delivered.

## Verification

Synthetic tests:
`backend/tests/test_saas_subscriptions.py` and
`backend/tests/test_saas_migrations.py` cover tenant isolation, role guards,
one-time activation, quota limits, missing-production-enrollment behavior,
migration upgrade/rollback and unimplemented paid activation.

Use GitHub Actions to verify the committed branch. This is a **code delivery**,
not proof of real healthcare, payment, or SaaS production readiness.
