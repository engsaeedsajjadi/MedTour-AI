# Verification log — 2026-10-14

Executed in an isolated build container:

```text
cd backend && pytest -q
............ [100%]
12 passed in 5.62s
```

Test coverage exercises:
- Authentication and invalid login.
- Consent prerequisite for patient case creation.
- Tenant A / Tenant B separation on case/patient access.
- Authorization for quotation approval.
- Physician verification requirement before referral and appointment booking.
- Manual booking confirmation reference requirement.
- Travel service cannot be confirmed without external reference.
- Secure document upload fails closed until storage is configured.
- Persian/Arabic/Pashto/Dari/English initial intake and one Arabic emergency keyword.
- Case status transitions, handoff, messages and audit events.
- AI provider requires consent and remains disabled by default.
- WhatsApp signed webhook validation and disabled integration state.

Frontend: 16 TypeScript/TSX files syntactically parsed with the TypeScript compiler, 0 parse errors. `npm install` and `next build` **not run**, since this container cannot access the npm registry. UI/browser integration remains unverified.

Docker Compose startup not run; no Docker daemon or external databases exercised. PostgreSQL Row-Level Security is not yet enforced. No clinician, legal or penetration test has been performed.

Do not claim the product is ready for real patients.
