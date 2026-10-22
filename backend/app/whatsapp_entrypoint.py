"""Public-only Meta WhatsApp webhook gateway.

Mount exactly the signed WhatsApp GET verification and POST receipt routes.
The admin API and patient portal MUST NOT be exposed as webhook ingress.
Even this gateway remains disabled without approved provider/legal processing
and is not independently authorized to handle real PHI in the alpha release.
"""
from fastapi import FastAPI
from fastapi.routing import APIRoute

from .whatsapp import router as whatsapp_router

app = FastAPI(
    title="MedTour WhatsApp Public Gateway",
    version="0.5.0-alpha",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.router.routes.clear()
app.router.routes.extend(whatsapp_router.routes)

assert len(app.routes) == 2
assert all(isinstance(route, APIRoute) for route in app.routes)
assert {
    (route.path, tuple(sorted(route.methods)))
    for route in app.routes
} == {
    ("/api/v1/webhooks/whatsapp", ("GET",)),
    ("/api/v1/webhooks/whatsapp", ("POST",)),
}
