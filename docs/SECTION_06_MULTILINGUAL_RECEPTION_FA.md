# MedTour AI — Section 06: Multilingual Receptionist (FA)

**Date:** 2026-10-23. **Scope:** local development with synthetic examples only. No approval for production medical use.

## Delivered implementation

1. Five text languages: Persian (fa), Arabic (ar), English (en), Pashto (ps), Dari (prs). Correct RTL/LTR metadata is exposed. No automatic language detection or native-speaker QA is claimed.
2. backend/app/receptionist.py: a conservative, deterministic administrative dispatcher for greeting, appointment, quote, documents, visa/travel, human operator, and general requests. All responses say that no appointment/visa/pricing/clinical decision is confirmed by chat.
3. backend/app/intake.py: precautionary emergency keyword normalization using Unicode NFKC, alternate Persian/Arabic letter forms, combining marks and zero-width separators. Emergency expressions are checked across languages; lexical flagging is NOT medical triage or safety clearance.
4. backend/app/patient_portal.py: only a valid patient portal token and active communication consent may send a message. Selected language is preserved on messages. Explicit human request and emergency flag force human handoff. No further automated messages appear on a handed-off conversation. No automatic WhatsApp/Telegram transmission occurs.
5. backend/app/main.py: urgent and explicit human requests are returned before calling the optional AI draft adapter. AI processing for other administrative drafts still requires specific consent, approved provider and human review.
6. Operator API: GET /api/v1/receptionist/catalog returns five-language coverage and explicit statuses for no validated clinical translation or speech. POST /api/v1/receptionist/preview accepts only a restricted intent and locale; rejects additional free-form patient text.
7. Frontend: /receptionist provides PHI-free operator previews; patient portal offers chat-language selection, localized warning/handoff labels and RTL/LTR composition. The staff inbox records manually reviewed outbound webchat replies in one of five selected languages.
8. The existing five-question structured medical-intake administrative flow continues unchanged. There is no autonomous medical matching, treatment recommendation, booking, price approval or visa issuance.

## Verification

- backend/tests/test_section_06_receptionist.py contains synthetic five-language route coverage, emergency Unicode normalization, consent and tenant guards, patient handoff, AI bypass and staff-only preview tests.
- Execute from backend directory: python -m pytest -q tests/test_section_06_receptionist.py, then python -m pytest -q.
- Require green Backend CI, real PostgreSQL 17/Redis 7 schema smoke job and Frontend TypeScript/Next.js verification before merging.
- All tests use synthetic statements. External approved provider calls and real patient information are prohibited.

## Remaining hard acceptance gates

- Native-speaker medical/administrative review in ALL five languages is NOT recorded. Copy cannot be called clinically or culturally validated.
- Independent clinical safety testing must assess emergency phrases, synonyms, false positives/negatives and emergency escalation. A keyword router is not an emergency service.
- STT/TTS voice and phone integrations, latency, accessibility and multilingual speech QA are NOT delivered in this section; voice remains separately tracked under master section 25.
- Cross-border data processing agreements, identity assurance, tenant RLS in live runtime, lawful Meta/Telegram/AI authorization and production privacy/security approval are not complete.

**Section 06 disposition:** local five-language administrative text routing and testable human handoff are implemented, subject to CI. Independent linguistic, clinical, voice and production acceptance remains open.
