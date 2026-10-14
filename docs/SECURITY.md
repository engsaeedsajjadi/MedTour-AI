# Security & privacy boundaries — v0.5.0-alpha

This repository has **not** passed an external security, privacy, clinical or regulatory audit. Do not store real patient records.

## Implemented controls (development baseline)

- Scoped tenant queries and roles at API boundaries; deny unauthorized cross-tenant patient/case operations; short-lived JWT; refresh rotation and logout revocation.
- Login attempt throttling: Redis counter in configured environments, in-memory only for dev/tests. Production denies login if Redis is unavailable.
- Purpose-specific consent records; one-time patient-attested consent link; withdrawal revokes portal access and pending outbound templates.
- Patient portal uses a high-entropy header token (no patient tokens in query URLs or logs). Identity must be independently assured in a production flow.
- Patient/staff document uploads enforce case ownership, purpose-specific consent, byte limit, magic bytes and SHA-256 checksum. Development encrypted files are marked **unscanned**.
- Production S3 adapter is disabled without all required approvals, KMS key, private bucket and ClamAV host. Malware scan fails closed; no public presigned URLs are issued.
- Signed HMAC inbound Meta webhook, tenant/account matching, idempotent receipt log, no storing unsupported unsolicited medical media.
- Outbound WhatsApp restricted to approved generic templates, human approval and explicitly enabled provider adapter. Any ambiguous send is placed in `needs_reconciliation`, never silently retried.
- AI is opt-in and human-reviewed. Stored AI logs must not contain prompts or patient medical content.

## Critical production gaps

1. **Database RLS:** current tenant filtering is application enforced; PostgreSQL RLS has NOT been activated. Implement tenant context and policies consistently, including portal access and webhook sessions, and test under PostgreSQL before production.
2. **Strong identity:** MFA for privileged users, verified patient identity and clinic/physician credential verification are incomplete.
3. **Document scanning:** end-to-end S3/KMS/ClamAV deployment, bucket policies, virus signatures/updates, object lifecycle, key rotation and incident response remain to be tested.
4. **Data privacy:** production privacy notice, privacy impact assessment, retention and erasure processes, cross-border data transfers and approved processors remain pending.
5. **Operations:** immutable external audit trail, central observability, secrets vault, WAF, infrastructure hardening, monitoring, backup restoration and penetration testing not independently validated.
6. **Messaging:** privacy rules, recipient country eligibility and approved templates must be verified for every market; no external provider approvals are part of this source package.
7. **Frontend:** browser security review, dependency audit, full semantic type checking, CSP, accessibility and E2E tests pending.

The AI must never diagnose, prescribe, promise treatment outcomes, approve visas, prices or confirmed appointments. Urgent symptoms require immediate local emergency escalation, with human review.
