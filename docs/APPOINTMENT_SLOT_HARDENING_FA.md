# Appointment slot integrity — development-only hardening

Updated: 2026-10-22, feature branch `enterprise/complete-gaps-2026-10-22`.

## Delivered

- Requests may share the same proposed timestamp, but only one appointment
  per tenant + physician + **exact instant** may have status `confirmed`.
- API performs tenant-scoped duplicate pre-check, then relies on a unique
  partial database index to resolve concurrent confirmation races.
- A confirmed appointment can be cancelled by an authorized admin ONLY with
  an independent cancellation reference. The original confirmation reference
  remains unchanged; cancellation reference and timestamp are recorded.
- Once the original confirmed slot is cancelled, the same exact slot can be
  confirmed for another request after fresh external/provider verification.
- Alembic revisions `9a4e1ce5039b` and `46bd9d1847ae`, metadata index,
  and synthetic API/migration regression tests included.

## Important limitations

This checks **exact instants**, NOT overlapping procedure durations,
physician time zones, operating hours, hospital resources or authoritative
provider calendars. A row marked `confirmed` reflects an operator-entered
external reference; the platform has not verified that external reference
against a real hospital/doctor system. No automated patient notification,
calendar sync, rescheduling, insurance or clinical approval is delivered.

## Pre-migration data audit

Before applying this migration to any existing database, an authorized
operator must run a read-only check and independently reconcile duplicates:

```sql
SELECT tenant_id, physician_id, requested_at, count(*) AS confirmed_count
FROM appointments
WHERE status = 'confirmed'
GROUP BY tenant_id, physician_id, requested_at
HAVING count(*) > 1;
```

**Do not automatically delete or reassign existing medical appointments.**
A conflicting production dataset will cause the unique-index migration to
fail, intentionally. Take a verified backup, review data-protection impact,
test in an isolated database clone, obtain operator signoff, then schedule a
separate production migration. No real provider calendar has been tested.
