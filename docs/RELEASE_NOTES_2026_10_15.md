# Development release notes — 2026-10-15

This release continues the original MedTour AI foundation; it does **not** claim completion of the master 45-point enterprise acceptance contract.

## Added

- Operational tracking with state machine, independent confirmation references and event history.
- Agent referrals, verified manual money entries, service-price provenance, quote line items.
- Five-language CMS draft/publish and approved knowledge base.
- Patient portal: revocable time-limited access, journey, safe web chat + emergency keyword-to-human escalation.
- Verified-specialty administrative provider search.
- Structured, staff-operated case intake sessions.
- Approved-provider-only translation draft route with separate AI processing consent.
- Gated official Meta webhook for existing consented contacts: signed payload, configured tenant routing, idempotency and quarantine of unknown contacts.
- Development-only AES-GCM encrypted private file upload/download for synthetic documents; no production claim.
- Additional Persian admin pages and a multilingual CMS public page template.
- 16 new backend tests; 28 total tested using synthetic SQLite.
- Master enterprise delivery matrix and step-by-step Windows local testing guide.

## Known limits

- No production-ready secure object storage/malware scanning; dev-only storage is disabled by default.
- WhatsApp outbound not implemented/activated; eligibility must be verified independently.
- No activated compliant LLM integration or clinical-quality multilingual AI.
- No verified production migrations, RLS, MFA, real hospital APIs, booking, finance settlement or visa issuance.
- Frontend package install and typecheck could not be completed in build environment without npm registry access; browser E2E pending.
- No upstream source code has been merged, copied, or sublicensed into this repository; upstream projects remain reviewed references.
