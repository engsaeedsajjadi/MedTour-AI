# Upstream software discovery and licensing

The MedTour AI foundation was designed after reviewing these public GitHub projects. **No upstream code was copied into this repository.** Architecture and domain flows were inspired by publicly described functionality and written independently.

| Repository | Reuse strategy | License considerations |
| --- | --- | --- |
| [HealthJourney](https://github.com/sartaj04/AI-Powered-Patient-Journey-Platform) | Primary reference for Next.js/FastAPI/Postgres, patient intake, RLS, workflow, Twilio concepts. Evaluate whether to adopt as core later through a dedicated audited fork. | MIT; keep attribution if code is imported. Source is early-stage, authors warn against use with real PHI. |
| [Nile Care](https://github.com/YoumnKaram561/Nile-Care) | Reference for doctor, hotel and transport journeys; optionally migrate validated domain logic. | MIT; .NET/SQL Server tech divergence. Existing medical file serving deserves security review. |
| [Medplum](https://github.com/medplum/medplum) | Future FHIR clinical repository integration; avoid unnecessary EHR duplication. | Apache 2.0; notice and attribution requirements if vendored. |
| [Medplum Patient Intake Demo](https://github.com/medplum/medplum-patient-intake-demo) | Reference for FHIR QuestionnaireResponse/Patient. | Apache-2.0 reported; validate each import. |
| [Medplum Voice Intake](https://github.com/deepgram-devs/medplum-patient-intake-deepgram) | Reference for voice intake design. | Apache-2.0 reported; check speech licensing. |
| [Chatwoot](https://github.com/chatwoot/chatwoot) | Preferred separate operator inbox to integrate over API; do NOT vendor or rewrite. | Mixed: core MIT, `enterprise/` requires a commercial subscription. |
| [MedPort](https://github.com/yashar2028/MedPort/tree/medport_prod) | Reference for cosmetic marketplace/provider catalog only. | No clear general code license found; do not reuse without permission. |

**Decision:** This delivery is a compact original foundation and upstream integration plan. The public HealthJourney codebase has NOT been merged. Integrating multiple full frameworks blindly would create conflicting authentication and medical-data models; a separate audit/migration plan is required before incorporating upstream code.
