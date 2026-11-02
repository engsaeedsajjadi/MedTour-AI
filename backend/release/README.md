# Production release sign-off

The API refuses to run with `APP_ENV=production` until `PRODUCTION_APPROVAL.json` exists here
with every reference filled in (see `backend/app/release_approval.py`). Add it only through a
reviewed pull request, after the independent reviews have actually taken place:

- penetration test by an independent party
- clinical safety review
- privacy impact assessment (DPIA) for the target countries
- backup and restore drill on the production infrastructure
- contracts with AI, messaging, payment, email/SMS and storage providers

At least two approvers must be named. Never create this file to make a deployment start.
