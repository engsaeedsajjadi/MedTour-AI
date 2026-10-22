# MedTour AI — Section 05: WhatsApp-first & alternate channel coordination

**Date:** 2026-10-22 · Development alpha. No real patient data, clinical assessment, live booking or unapproved external channel use.

## Delivered architecture

- **Primary channel: WhatsApp Cloud API.** Signed `X-Hub-Signature-256` webhook, strict configured phone-number account and tenant mapping, 256 KiB inbound cap, JSON content type and shape checks, replay-safe message receipts, consent-before-storage, media quarantine and human handoff. There is NO automated response, AI medical advice or passive creation of a patient account from an unknown phone number.
- **Separate public ingress application:** `uvicorn app.whatsapp_entrypoint:app` mounts *only* GET verification and POST webhook routes, not staff login, patient portal, documents, admin UI or open API docs. Even the isolated gateway refuses `APP_ENV=production` in this non-approved alpha. Do not deploy it with real patient traffic.
- **Outbound templates:** Only configured generic administrative WhatsApp templates, opt-in communication consent, admin approval and optional durable worker can request an official provider send. No free-form WhatsApp responses, medical records, clinic guarantees, autonomously approved appointments or attached reports. `app.delivery` performs an atomic outbox claim and treats timeouts as `needs_reconciliation` without automatic retries.
- **Delivery receipts:** A signed Meta receipt now updates only the matching tenant-scoped, WhatsApp-channel outbox entry by provider message ID. `delivered` and `read` advance monotonically; `failed` after `sent` requires reconciliation. Identical receipts are deduplicated with hashed event keys; raw delivery payloads and clinical details are not stored in the receipt event table. Earlier receipts with no matching sent message remain metadata only: they never authorize a send.
- **Telegram fallback:** Existing independent `app.telegram_entrypoint:app` serves public onboarding-only generic warnings in fa/ar/en/ps/prs. Telegram chat ID does not prove a MedTour patient identity, and no Telegram content or documents are routed into patient CRM or AI.
- **Secure-portal alternate route:** Existing authenticated patient portal is the only development route for consented patient interaction; identity assurance for real PHI is not yet complete. Staff-only `GET /api/v1/channels/readiness` reports configured vs externally verified states honestly. `GET /api/v1/channels/patients/{id}/options` is tenant-scoped and requires no provider request. `POST /api/v1/channels/cases/{id}/secure-portal-handoff` requires active communication consent; it records one open generic staff task and audit, issues NO patient token and sends NO external message. Consent withdrawal cancels any pending handoff tasks.
- **Operator UX:** `/messaging` displays WhatsApp-first/fallback readiness and lets staff create a secure-portal invitation task. Existing WhatsApp template outbox and human translation review remain separate from this manual handoff.

## Activation boundaries and truthful status

The following capabilities still require external prerequisites **that this repository cannot grant**: Meta for Developers/WhatsApp Business eligibility and approved template names/locales, reachable HTTPS webhook and independent network/auth controls, vendor processing agreements, secure patient identity/clinical consent and full per-tenant RLS in the active application runtime. Live Meta/Telegram deliveries must be tested with authorized sandbox/business accounts by the operator. The user previously reported Meta Developer restrictions, so there is no basis for claiming a live WhatsApp test.

For Telegram, use official BotFather and the [existing onboarding guide](TELEGRAM_CHANNEL_MVP_FA.md); **never** send bot tokens or webhook secrets in ChatGPT or commit them. Email or SMS channels are NOT implemented or claimed by this patch. Patient fallback means a human-prepared secure-portal invitation, not automated forwarding or cross-channel copying of sensitive text.

## Verifiable tests

- `backend/tests/test_section_05_channels.py`: standalone public route exposure, signed status receipts, duplicate/monotonic updates, failed receipt reconciliation without retry, invalid account and media type rejection, duplicate incoming event in a batch, consent and tenant restrictions, duplicate handoff task and cancellation on consent withdrawal.
- Existing `backend/tests/test_telegram.py`, consent and worker tests must continue to pass.
- Backend and frontend GitHub Actions, PostgreSQL 17/Redis 7 integration and TypeScript/build must pass on final commit.
- Pending acceptance: actual approved Meta webhook ingress, authenticated staff workflows under production PostgreSQL RLS, real five-language human review and language-specific template approval, Chatwoot integration and authorized real-world operational pilot.

**Section 05 decision:** Local signed transport, conservative outbound receipt tracking and human-only secure-portal fallback delivered, subject to CI. Real WhatsApp/Telegram and full enterprise patient messaging still gated and **not accepted for Production**.
