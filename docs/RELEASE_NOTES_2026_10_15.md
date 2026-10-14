# MedTour AI Enterprise v0.5.0-alpha — Change log

- Added patient-attested one-time consent challenges, preview endpoint and multilingual-capable consent page; consent withdrawal invalidates portal access and pending outbound tasks.
- Added login rate limiting, optional Redis production backend, safe response headers, ready endpoint and Docker Redis service.
- Added Alembic baseline migration for fresh databases and BigInteger financial minor-unit columns.
- Added a fail-closed S3 private-object adapter with SSE-KMS, ClamAV INSTREAM scan and SHA-256 integrity checks; real infrastructure has not been exercised.
- Added portal and staff multipart document upload workflows, private document list and consent revocation guards; encrypted local storage stays development-only.
- Added administrative five-language questionnaires and patient-facing structured intake with human escalation and emergency warning handling.
- Added consent-gated translation draft creation and operator approval for secure web chat only.
- Added official WhatsApp generic-template outbox with human approval and idempotency plus explicit delivery CLI that is disabled without required business/provider approvals. Uncertain external outcomes require manual reconciliation.
- Added new frontend pages for messaging approval and patient consent, and enhanced patient portal with intake and document uploads.
- Added 13 synthetic tests versus prior 31: **44 passing backend tests**; migration smoke test successful. No live integrations or Next.js production build verified.

Not delivered: full original 45-part enterprise scope, strong patient identity, PostgreSQL RLS, complete SaaS billing, licensed medical/hotel/visa API integrations and production certification.
