"""Privacy-preserving HTTP request correlation for operational diagnostics.

No request body, query string, IP address, email, access token or raw error
details are recorded. Log aggregation and SLO alerting require external setup.
"""
from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger('medtour.http')


class SafeRequestTraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            route = request.scope.get('route')
            # Route templates like /patients/{patient_id} are safe; raw URL is not.
            template = getattr(route, 'path', None)
            if not isinstance(template, str) or not template.startswith('/'):
                template = '<unmatched>'
            duration = max(0.0, (time.perf_counter() - start) * 1000)
            log.info(json.dumps({
                'event': 'http_request',
                'request_id': request_id,
                'route': template,
                'method': request.method,
                'status': status,
                'duration_ms': round(duration, 2),
            }, separators=(',', ':')))
