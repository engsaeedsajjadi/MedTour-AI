"""Isolated public-facing ASGI entrypoint for a Telegram onboarding webhook.

Unlike app.main this application mounts no staff login, tenant database,
patient portal, document, medical AI or internal operational routes.
Do not expose the administrative API to the public merely to run this bot.
"""
from fastapi import FastAPI
from .telegram import router as telegram_router

app = FastAPI(
    title="MedTour Telegram Onboarding Gateway",
    version="0.5.0-alpha",
    description="Privacy notice and secure portal handoff only. No PHI ingestion.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# Keep precisely one audited FastAPI APIRoute across FastAPI/Starlette versions.
# Recent FastAPI may register include_router() as an internal _IncludedRouter
# object rather than materializing the path in app.routes. Directly register
# the already-audited staged route and clear all framework routes first.
app.router.routes.clear()
app.router.routes.extend(telegram_router.routes)

# A deployment gate: no accidental admin/PHI endpoint may leak into this entrypoint.
assert len(app.routes) == 1 and app.routes[0].path == "/api/v1/webhooks/telegram"
assert getattr(app.routes[0], "methods", set()) == {"POST"}
