# MedTour AI — Section 02: Non-negotiable safety principles

**Date:** 2026-10-22  
**Scope:** Development-mode safeguards only. There is no authorization to process actual patient health data or to use this as a clinical product.

## Enforced software-level guarantees

1. **No production shortcut:** The main FastAPI application fails at startup when APP_ENV=production, regardless of a user-supplied 'production ready' flag. There is no override in this alpha code. Independent release engineering must replace this with evidence-backed release gates after sections 26/27/28/32 and external approvals are complete. The isolated public Telegram onboarding gateway is separate and does not expose patient/admin endpoints.
2. **No autonomous clinical action:** AI drafts are staff-reviewed administrative suggestions only. Existing case workflow still requires qualified humans for treatment-related actions. No diagnosis, prescription, promises of treatment outcome, independent admission, visa issuance, or booking claim is implemented.
3. **Current purpose-specific consent:** Both staff-recorded withdrawal and one-time patient-link withdrawal use one transactional cancellation handler; either path revokes portal grants and blocks approved/queued outbound templates. If the withdrawn purpose is communication or AI processing, any pending translations linked to that patient are blocked and their source/draft text scrubbed (approved historical messages need separate retention/erasure review).
4. **AI translation review checks current processing consent:** Existing pending translation cannot be approved after a consent revocation even if cancellation was bypassed by a legacy direct DB write. A renewed consent cannot restore a previously blocked draft. Patient/tenant constraints are verified.
5. **Explicit AI processor destination:** Optional AI calls require AI_PROVIDER_APPROVED=true, configured credentials, and a precisely matched hostname in AI_APPROVED_HOSTS. Only HTTPS, standard TLS port, no embedded credentials/query/fragment, no IP literal or localhost. A secure environment still needs DNS and network egress restrictions, vendor DPA and regulatory review.
6. **Truthful machine-readable status:** GET /api/v1/safety/contract always reports production_ready=false and that patient data/automated diagnosis are not authorized. These are actual alpha limitations, not a marketing label.
7. **Independent high-risk approvals:** Existing staff API keeps admin approval for quote, appointment, travel and section-01 high-stakes case milestones. External reference strings are attestations, not independently verified real-world transactions.

## Tests and evidence

- backend/tests/test_section_02_safety.py: alpha runtime rejection, public policy status, both withdrawal routes, data scrubbing/tenant isolation, stale consent prevention, exact AI host matching.
- Execute: cd backend && python -m pytest -q tests/test_section_02_safety.py && python -m pytest -q
- GitHub Actions backend and frontend workflows must pass on the final commit before merge. Do not call the feature complete without observing these results.
- Cross-process/race testing, external API tests, real data, penetration testing and load tests are out of scope for this synthetic suite.

## Explicit pending external acceptance gates

**NOT complete:** PostgreSQL RLS migration in primary runtime, physician/patient identity assurance/MFA, full retention and subject erasure process, external privacy impact assessment and cross-border medical data processing agreements, independently reviewed emergency escalation policy, verified treatment providers and clinical safety approval, S3/KMS/ClamAV deployed and tested, approved WhatsApp/Telegram/AI processing, external booking/visa permissions, payment controls and complete E2E/security testing.

**Section 02 acceptance decision:** Technical alpha policy guards may be accepted after CI passes. **Enterprise operational / regulatory / clinical acceptance remains open.** Do not use real patient information.
