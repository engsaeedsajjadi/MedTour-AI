# Security review / production release blockers

**Development only**. Do not import actual medical files or identifying patient data until all of the following are addressed.

1. Confirm all relevant healthcare, tourism, privacy, cross-border processing, and vendor eligibility obligations. Require clinical governance and written partner contracts.
2. Implement production migration system and FORCE ROW LEVEL SECURITY on all tenant tables; add cross-tenant DB tests with separate credentials. Current explicit query filters are not enough for Enterprise certification.
3. Encrypt documents in private object storage; use scan-before-read, short-lived signed links, protected metadata, upload lifecycle, retention policy and removal access logs. Current upload intentionally fails closed.
4. Implement MFA for privileged accounts, short sessions, refresh token rotation and revocation, breached-password screening and rate limits / anti-brute force.
5. Implement server-to-server consent collection signed by the patient/representative, consent revocation enforcement, notice history and legal hold/retention.
6. Keep PII and PHI out of telemetry, URL paths, prompts and debug logs; require DPA and region checks for LLM, speech and messaging providers.
7. Audit all endpoints for assignment-level/relationship-level authorization; current operator can access all patients within the tenant, which may not meet least-privilege requirements.
8. Validate provider credentials, privileges and sanctions; ensure physician approval of any treatment plan and emergency routing oversight.
9. Add immutable audit and incident response, key/secret rotation, backup restore drills, penetration tests, scanning and disaster recovery.
10. WhatsApp Business Cloud API activation only if Meta officially authorizes the business and flows. Web chat remains the fallback. Respect opt-in and message-template restrictions.
11. Do not enable external payment processing unless gateway legal eligibility, identity verification, webhook security and reconciliation are complete.
12. Confirm quotations and bookings using verified sources; visas must never be marked approved by the app itself.

Authentication implemented here is a **foundation** only. No claim is made of HIPAA, GDPR or ISO certification or of compliance with the law of any particular country.
