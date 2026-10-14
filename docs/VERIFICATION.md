# Verification — 2026-10-15 — v0.5.0-alpha

Environment: Python 3.13 build container, local SQLite for *synthetic-only tests*. Production application is targeted at Python 3.12 / PostgreSQL 17.

```text
cd backend && pytest -q
............................................                             [100%]
44 passed in 20.15s
```

Also exercised:
- `python -m compileall -q backend/app` => completed.
- Alembic autogeneration / `alembic upgrade head` on new temporary SQLite => successful.
- `alembic check` on migrated temporary SQLite => no new upgrade operations detected (before the last schema regeneration; regenerated baseline subsequently upgraded and used by tests).
- TypeScript compiler AST parse of 30 source files before the consent screen, and separately checked frontend syntax after UI edits; full TypeScript semantic checks require installed npm dependencies.
- `docker-compose.yml` parsed as valid YAML.

Not executed / not verified:
- `npm run build`, full Next.js/React type-check and browser E2E: npm dependency install timed out in this environment.
- Docker container startup, actual PostgreSQL, S3/KMS/ClamAV and Redis network integration tests.
- Official WhatsApp outbound and AI model / speech provider integration.
- Security penetration testing, clinician evaluation, language expertise validation, legal audit, stress/performance benchmarking.

**Security statement:** these are local development verification results, not evidence of healthcare certification or live deployment readiness.
