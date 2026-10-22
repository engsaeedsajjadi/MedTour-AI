# MedTour AI — Section 04: Enterprise modules and unified case coordination

**Date:** 2026-10-22  
**Release:** development only, NOT permitted to store or process real patient health data.

## Implemented scope

Section 04 describes the integrated enterprise *module map*, while the deep requirements of each module are specified separately in sections 5–38. This change makes the previously scattered staff modules discoverable and supplies an authenticated, tenant-scoped administrative case workspace.

**Catalog** — GET `/api/v1/modules`: stable typed descriptors for 19 product domains, local UI routes and mapped master-prompt sections. States are explicit (`local_workflow`, `partial`, `external_gate`, `not_delivered`). This catalog is deliberately not a provider-availability indicator, a paid-plan entitlement check, or an external certification.

**Case hub** — GET `/api/v1/modules/cases/{case_id}`: enforces authenticated operator/admin and tenant ownership, reads consent-sensitive readiness from the existing mission service, counts case-scoped intake, documents, referrals, appointments, quotes, travel, operations and tasks, counts the patient's own conversations, shows administrative task states and active emergency-warning flag. No medical answers, messages, complaint text, filenames, contact details, document storage keys, price amounts or task titles are returned.

**Task coordination** — The existing `POST /api/v1/tasks` creates a tenant-scoped task after case ownership validation. New PATCH `/api/v1/modules/cases/{case_id}/tasks/{task_id}/status` supports `open <-> done` with a non-PHI administrative reference; concurrent writes use compare-and-swap. Both `CaseTimeline` and `Audit` are persisted in the same transaction. Cross-tenant and cross-case updates are rejected with 404.

**Tenant summary** — GET `/api/v1/modules/summary`: bounded count aggregates without person-identifiable response fields.

**Frontend** — `/modules` linked in staff navigation: truthful module states, tenant-scoped case selection, counts, readiness, manually recorded task completion and audit link. It does not automatically approve patient care, clinic access, insurance, payment, visa or travel.

No new tables or Alembic migrations are required; this consumes already-versioned entities.

## Verification

- `backend/tests/test_section_04_modules.py` contains synthetic cases for module-state truthfulness, authorization, isolation between tenants/patients/cases, response minimization, task state changes and repeat-state rejection.
- Existing backend tests, PostgreSQL 17 + Redis 7 stack job, and frontend TypeScript/build CI are mandatory for PR merge.
- Browser E2E testing with actual staff roles, performance/load, concurrency on real PostgreSQL, independent clinical/privacy/security audits and external provider availability are NOT established by this change.

## Remaining specialist module acceptance gates

Physician credentials, provider/hospital portals, capacity-safe scheduling, verified visa/hotel bookings, multi-currency payments, signed cost quotations, full multilingual language reviews, real messaging contracts, subscription billing and independent medical/legal review remain tracked in their dedicated master-prompt sections. Catalog entries and synthetic test pass must never be used to claim those completed.

**Section-04 local integration acceptance:** subject to green CI, internal registry + tenant-scoped case hub and task lifecycle can be marked implemented. **Enterprise product-wide acceptance remains open.**
