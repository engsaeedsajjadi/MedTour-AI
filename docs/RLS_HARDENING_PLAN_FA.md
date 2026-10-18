# MedTour AI — PostgreSQL RLS Hardening Plan (FA)
Date: 2026-10-18 — Evidence from local development database and repository inspection.

## Verified baseline
- PostgreSQL 17 local instance: 39 public tables. RLS disabled, FORCE disabled and 0 policies for all tables.
- The database role \`medtour\` has SUPERUSER, BYPASSRLS, CREATEDB and CREATEROLE, owns all 39 public tables, and is the actual API connection role.
- Existing backend API and synthetic tests include application-layer tenant checks. Passing tests do not prove database-layer tenant isolation.
- \`TenantEntity\` ORM mixin attaches non-null \`tenant_id\` to 37 operational tables. \`tenants\` and \`alembic_version\` require distinct treatment.
- Existing app uses pooled SQLAlchemy sessions without a PostgreSQL transaction-local, authenticated tenant context.
- Existing inter-table FKs typically reference \`id\` alone. Composite tenant-bound constraints require a separate compatibility audit.
- Database backup+isolated restore was tested; keep a verified backup for any future schema change.

## Security constraints
1. **Never turn on RLS in the existing database without first integrating all application paths and testing a restored clone.**
2. **Never use the SUPERUSER/BYPASSRLS/table-owner role as the runtime API principal.** Keep a privileged migrator separate and retain protected credentials.
3. Grant a non-owner \`medtour_app\` role only required DML permissions; no CREATE/ALTER/TRUNCATE/BYPASSRLS/GRANT ROLE. No direct \`tenants\` or \`alembic_version\` access unless justified.
4. Tenant row access uses an *authenticated* context scoped to each transaction. A policy pattern for tenant tables is: \`USING (tenant_id = NULLIF(current_setting('medtour.tenant_id',true),'')) WITH CHECK (tenant_id = NULLIF(current_setting('medtour.tenant_id',true),''))\`. This is illustrative, not an approved production policy.
5. **Caution:** custom PostgreSQL session variables can be set by ordinary SQL from the same connection. A raw \`SET medtour.tenant_id = ...\` value is *not* independently tamper-proof against arbitrary SQL injection. Treat it as defense in depth, not a substitute for injection prevention or a DB-verified context design.
6. Use \`set_config(..., true)\` *within each transaction*. Committing mid-request resets the setting; the SQLAlchemy Session lifecycle and all commit/rollback/reuse paths must be audited.
7. Keep PostgreSQL RLS policy evaluation, identifier authorization and cross-tenant FK integrity in scope. PostgreSQL foreign-key/uniqueness checks can bypass RLS; consider tenant-paired uniqueness and composite FKs.
8. Ensure backups, monitoring, cron, webhook and migration jobs have separately reviewed roles; do not grant blanket permissions to the runtime role.

## Special pre-auth flows
- Staff login: resolve tenant slug and verify login credentials without global unrestricted access to all staff records. Only a narrow auth bootstrap path should be allowed.
- Refresh rotation: resolve refresh hash securely, then establish authenticated tenant context; preserve replay detection and revoked family semantics.
- Patient portal / consent links: resolve high-entropy hash, validate tenant, expiry and revocation before accessing protected patient data.
- WhatsApp webhook: verify HMAC signature and tenant/account mapping, avoid unauthenticated cross-tenant reads.
- Public CMS: use a strictly read-only publishing mechanism or an approved minimal public retrieval function.
- Background workers and migrations: separate identities and explicit scoped approvals.

## Phases (do not run on live data until gates are satisfied)
A. Use \`scripts/rls-isolated-probe.ps1\` to validate PostgreSQL RLS semantics on *synthetic data* in a disposable, network-isolated PostgreSQL 17 container. No existing DB is read.
B. Create a dedicated, non-superuser API role and a privilege-mapped migration **only on a disposable clone**; confirm actual PostgreSQL table grants, no role escalation, and no owner bypass.
C. Implement a verified tenant context and scoped database sessions for every endpoint, including pre-auth and background paths. Add negative tests for missing/forged context and transaction-pool reuse.
D. Add RLS policies on all 37 tenant-scoped tables and audited policies/visibility for \`tenants\`; keep \`alembic_version\` migrator-only. Verify SELECT/INSERT/UPDATE/DELETE, including cross-tenant foreign key references.
E. Validate against real PostgreSQL (not only SQLite), Alembic upgrades, CI, full 48+ tests, API login/refresh/logout/portal/consent/webhook and rollback behavior.
F. Review separate database credentials, role ownership, backup-restoration procedure, monitoring and rollback. Only then stage a production-like pilot with approved synthetic data.

## What the isolated probe proves—and does not
The probe demonstrates that an unprivileged, non-owning PostgreSQL role cannot SELECT/INSERT/UPDATE another tenant's rows under a simple policy, and that a local setting is reset at commit. It does *not* exercise the MedTour ORM, live DB, login flows, SQL injection hardening or all 37 tables, and does not establish enterprise readiness.
