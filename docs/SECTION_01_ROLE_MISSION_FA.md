# MedTour AI — Section 01: Role and Mission (FA)

**Date:** 2026-10-22
**Branch:** enterprise/section-01-patient-mission-2026-10-22
**Scope:** International patient **administrative coordination**, not provision of medical care.

## Mission and responsibility boundaries

The platform receives patients seeking care in Iran, records purpose-specific consent, provides five-language structured intake, routes urgent flags to humans, supports manual physician/appointment review, supervised quotation and travel, operator messaging, and administrative follow-up.

It does **not** diagnose, prescribe, autonomously select treatment, actually reserve hotels/appointments, issue visas, verify border arrivals, send payment, or prove providers completed services. External records and professional judgments require responsible human/partner verification. No real patient records may be used in this alpha build.

## Delivered coordination control

- Staff can read GET /api/v1/cases/{case_id}/mission: tenant-limited readiness across active intake/communication consents, structured intake submission, urgent flags, verified provider referral, approved quotation, manually verified confirmed appointment, resolution of *recorded* travel requests, and approved follow-up operation. No patient medical text in payload.
- PATCH /api/v1/cases/{case_id}/status enforces prerequisites. Missing evidence blocks progression with HTTP 409 and machine-readable list. It does not bypass existing state transition map.
- Critical milestones confirmed, arrived, in_treatment, follow_up and closed require admin + explicit human reference; references are administrative attestations, **not proof of a completed medical procedure**.
- Each successful transition generates a tenant-scoped case timeline and existing audit event. GET /api/v1/cases/{case_id}/mission/history reveals these events to staff only.
- A detected emergency intake remains blocking; no automatic AI or administrative clearance route.
- Operator interface at /journey displays readiness, missing prerequisites, administrative history, and next status actions. References must not contain PHI.
- No schema change: existing CaseTimeline table is used.

## Operational journey and guards

1. Staff creates patient + explicit intake consent, then case. New -> intake.
2. Patient/staff submits the five structured intake questions. An emergency flag prevents advance into review.
3. Intake -> review_pending -> provider_review; approved referral must reference a manually verified physician before quote_pending.
4. Approved quote must be recorded before quote_sent; confirmed additionally needs confirmed appointment with independently recorded external reference to the same referred physician.
5. Confirmed -> travel_planning. Unresolved travel requests block arrived; no travel request means none is required, but human administrative arrival attestation is still needed.
6. Arrived -> in_treatment -> follow_up each require responsible admin + evidence reference.
7. Follow_up -> closed requires separately human-approved followup operation and an admin closure reference.

## Verification

Synthetic API test: backend/tests/test_case_mission.py, tests cover cross-tenant access, absence of authorization, emergency block, consent withdrawal, skipped milestones, operator/admin separation and all 11 state transitions. Run from backend: python -m pytest -q tests/test_case_mission.py then python -m pytest -q. Production acceptance requires independent backend/portal E2E, PostgreSQL RLS runtime, security & clinical/privacy sign-offs, provider contracts, translated medical QA and operational trial; GitHub tests cannot replace these.

## Acceptance status

**Local coordination implementation accepted by CI: 180 backend synthetic tests passed (1 warning), and frontend CI passed, 2026-10-22.** Evidence: [Backend GitHub Actions](https://github.com/engsaeedsajjadi/MedTour-AI/actions/runs/39802835945) and [Frontend GitHub Actions](https://github.com/engsaeedsajjadi/MedTour-AI/actions/runs/39802835984). **Real-world mission NOT accepted** until external provider, clinical, privacy and security gates are satisfied.
