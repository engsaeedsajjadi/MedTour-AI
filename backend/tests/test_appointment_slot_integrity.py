"""Synthetic physician scheduling conflicts and evidence-preserving cancellation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_confirmed_physician_slot_is_unique_until_evidenced_cancellation(seeded):
    (client, auth, _, _), admin, first_patient, first_case = seeded

    physician = client.post('/api/v1/physicians', headers=admin, json={
        'full_name': 'Synthetic Physician', 'specialty': 'cardiology', 'city': 'Tehran'
    })
    assert physician.status_code == 201, physician.text
    doctor_id = physician.json()['id']
    verify = client.patch('/api/v1/physicians/' + doctor_id + '/verification',
                          headers=admin, json={'status': 'verified'})
    assert verify.status_code == 200, verify.text

    other_patient = client.post('/api/v1/patients', headers=admin, json={
        'full_name': 'Second Synthetic Patient', 'language': 'en'
    }).json()
    assert client.post('/api/v1/consents', headers=admin, json={
        'patient_id': other_patient['id'], 'purpose': 'intake',
        'accepted': True, 'notice_version': 'v1'
    }).status_code == 201
    other_case_response = client.post('/api/v1/cases', headers=admin, json={
        'patient_id': other_patient['id'], 'complaint': 'Synthetic request',
        'specialty': 'cardiology'
    })
    assert other_case_response.status_code == 201, other_case_response.text
    second_case = other_case_response.json()

    instant = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        second=0, microsecond=0
    ).isoformat()
    def book(case_id):
        return client.post('/api/v1/appointments', headers=admin, json={
            'case_id': case_id, 'physician_id': doctor_id, 'requested_at': instant
        })

    first = book(first_case['id'])
    second = book(second_case['id'])
    assert first.status_code == 201 and second.status_code == 201
    first_id, second_id = first.json()['id'], second.json()['id']

    def transition(appt_id, status, reference=None):
        payload = {'status': status}
        if reference is not None:
            payload['reference'] = reference
        return client.patch('/api/v1/appointments/' + appt_id + '/status',
                            headers=admin, json=payload)

    confirm = transition(first_id, 'confirmed', 'provider-confirm-001')
    assert confirm.status_code == 200, confirm.text

    conflict = transition(second_id, 'confirmed', 'provider-confirm-002')
    assert conflict.status_code == 409, conflict.text
    assert transition(first_id, 'cancelled').status_code == 422

    cancelled = transition(first_id, 'cancelled', 'provider-cancel-001')
    assert cancelled.status_code == 200, cancelled.text
    state = cancelled.json()
    assert state['status'] == 'cancelled'
    assert state['confirmation_reference'] == 'provider-confirm-001'
    assert state['cancellation_reference'] == 'provider-cancel-001'
    assert state['cancelled_at'] is not None

    rebooked = transition(second_id, 'confirmed', 'provider-confirm-002')
    assert rebooked.status_code == 200, rebooked.text
    assert rebooked.json()['status'] == 'confirmed'
    assert transition(first_id, 'confirmed', 'provider-confirm-003').status_code == 409
    assert client.patch('/api/v1/appointments/' + second_id + '/status',
                        headers=auth('b'), json={
                            'status': 'cancelled', 'reference': 'not-authorized'
                        }).status_code == 404
