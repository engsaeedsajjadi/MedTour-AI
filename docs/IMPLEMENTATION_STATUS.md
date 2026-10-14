# Implementation status — 2026-10-14

Legend: **IMPLEMENTED**=functional source + tests where noted; **FOUNDATION**=limited integration; **BLOCKED**=external consent/eligibility/access; **PLANNED**=not built.

| Feature | State | Note |
| --- | --- | --- |
| Git repository source and local commit | IMPLEMENTED | See release ZIP and git history. Remote GitHub creation/push requires repo creation capability. |
| FastAPI and relational data models | IMPLEMENTED | PostgreSQL in Compose; SQLite tests. |
| Login, short-lived JWT, user roles | IMPLEMENTED | Development provisioning only; token revocation and MFA remain. |
| Tenant-scoped endpoints | FOUNDATION | Explicit tenant checks and tests. PostgreSQL RLS + production migrations remain. |
| Patient registration and active intake consent | IMPLEMENTED | Operator workflow with consent required for cases. |
| Case workflow and audit | IMPLEMENTED | Controlled state transitions. |
| Physician and hospital registration | IMPLEMENTED | Verification is human-controlled. |
| Referral and appointment workflow | IMPLEMENTED | Appointment requires manual confirmation reference. |
| Treatment quotation draft and approval | IMPLEMENTED | Manual estimate, no external pricing data. |
| Visa, hotel, interpreter, transport requests | FOUNDATION | Manual request tracking, NOT real bookings/visa issuance. |
| Conversation records and human handoff | FOUNDATION | Internal WebChat records only; patient messaging UI and incoming webhook not implemented. |
| Arabic, English, Persian, Pashto, Dari | FOUNDATION | Structured prompts, not fluent LLM translations. |
| AI medical interview, GPT/Gemini | PLANNED | No AI provider keys or medical NLP are configured. |
| Emergency messages | FOUNDATION | Keyword warnings only. NOT reliable emergency triage. |
| PDF/image secure upload | BLOCKED | Explicitly returns 503 until private encrypted storage and malware scan are integrated. |
| WhatsApp Business Cloud API | BLOCKED | Official eligibility, agreements, opt-in and regulatory review required. |
| Doctor portal, hospital portal, patient portal | PLANNED | Backend needs resource-level permissions and dedicated user flows. |
| Currency rate retrieval, payments, real bookings | PLANNED | No production external integrations. |
| Multi-tenant SaaS billing, representatives | PLANNED | Separate design phase. |
| Frontend Arabic/Pashto/English localization | PLANNED | Admin is Persian RTL; backend has five-language initial prompts. |
| End-to-end deployment and security certification | PLANNED | NOT production ready. |

**Verified:** API tests in `backend/tests/` run locally using in-memory synthetic patients. Frontend packages require installation/build in an environment with npm registry access; not verified in this isolated build environment.
