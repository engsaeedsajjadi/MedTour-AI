"""Privacy regression tests for correlation logging (synthetic strings only)."""
from __future__ import annotations
import json
import logging
import re


def test_trace_id_and_safe_route_template_do_not_log_patient_details(context, caplog):
    client, auth, _, _ = context
    admin = auth('a')
    canary = 'SYNTHETIC_PRIVATE_MEDICAL_TEXT_SHOULD_NOT_LOG'
    with caplog.at_level(logging.INFO, logger='medtour.http'):
        response = client.post(
            '/api/v1/patients?search=' + canary,
            headers=admin,
            json={'full_name': canary, 'language': 'en'}
        )
    assert response.status_code == 201, response.text
    trace = response.headers.get('X-Request-ID', '')
    assert re.fullmatch(r'[0-9a-f]{32}', trace)
    ours = [json.loads(r.message) for r in caplog.records
            if r.name == 'medtour.http' and r.message.startswith('{')]
    assert ours
    event = ours[-1]
    assert event['request_id'] == trace
    assert event['route'] == '/api/v1/patients'
    assert event['status'] == 201
    assert event['duration_ms'] >= 0
    assert 'patient' not in event.keys()
    assert canary not in '\n'.join(r.message for r in caplog.records
                                  if r.name == 'medtour.http')


def test_unmatched_route_does_not_expose_raw_path(context, caplog):
    client, _, _, _ = context
    marker = 'SYNTHETIC_PRIVATE_IDENTIFIER'
    with caplog.at_level(logging.INFO, logger='medtour.http'):
        response = client.get('/no-such-route/' + marker)
    assert response.status_code == 404
    ours = [json.loads(r.message) for r in caplog.records
            if r.name == 'medtour.http' and r.message.startswith('{')]
    assert ours[-1]['route'] == '<unmatched>'
    assert marker not in ours[-1].values()
