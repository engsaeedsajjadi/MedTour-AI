"""Synthetic tenant subscription tests; never touch payment providers or patient data."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Case, Patient
import app.subscriptions as saas


def test_free_plan_activation_is_admin_only_tenant_isolated(context):
    client, auth, ids, Session = context
    admin = auth('a')
    other = auth('b')
    operator = auth('a', 'operator@example.test')

    assert client.get('/api/v1/saas/plans', headers=operator).status_code == 403
    assert client.post('/api/v1/saas/subscription/activate-free', headers=operator).status_code == 403
    assert client.get('/api/v1/saas/subscription', headers=admin).json()['status'] == 'unprovisioned'

    response = client.post('/api/v1/saas/subscription/activate-free', headers=admin)
    assert response.status_code == 201, response.text
    assert response.json() == {
        'status': 'active', 'plan_code': 'FREE', 'payment_collected': False
    }
    assert client.post('/api/v1/saas/subscription/activate-free', headers=admin).status_code == 409

    assert client.get('/api/v1/saas/subscription', headers=admin).json()['plan_code'] == 'FREE'
    assert client.get('/api/v1/saas/subscription', headers=other).json()['status'] == 'unprovisioned'
    assert client.get('/api/v1/saas/usage', headers=other).json()['counts']['patients'] == 0
    assert client.get('/api/v1/saas/usage', headers=admin).json()['counts']['users'] == 2
    assert client.post('/api/v1/staff', headers=admin, json={
        'email': 'third@example.test', 'password': 'synthetic_staff_pass_123',
        'role': 'operator'
    }).status_code == 409

    with Session() as db:
        from app.models import Audit
        assert db.scalar(select(func.count()).select_from(Audit).where(
            Audit.tenant_id == ids[0], Audit.event == 'saas_free_plan_activated'
        )) == 1


def test_enrolled_tenant_quota_blocks_additional_patients_and_cases(context, monkeypatch):
    client, auth, ids, Session = context
    admin = auth('a')
    other = auth('b')
    monkeypatch.setattr(saas, 'PLANS', {
        'FREE': {'patients': 2, 'cases': 1, 'users': 2}
    })
    assert client.post('/api/v1/saas/subscription/activate-free', headers=admin).status_code == 201

    patients = []
    for i in range(2):
        response = client.post('/api/v1/patients', headers=admin, json={
            'full_name': f'Synthetic Test Patient {i}', 'country': 'AF', 'language': 'en'
        })
        assert response.status_code == 201, response.text
        patients.append(response.json())
    blocked = client.post('/api/v1/patients', headers=admin, json={
        'full_name': 'Third Synthetic Patient', 'language': 'en'
    })
    assert blocked.status_code == 409, blocked.text
    assert client.get('/api/v1/saas/usage', headers=admin).json()['counts']['patients'] == 2

    # Tenant B is not charged to tenant A and is not blocked by A's cap.
    assert client.post('/api/v1/patients', headers=other, json={
        'full_name': 'Tenant B Synthetic Patient', 'language': 'en'
    }).status_code == 201

    for p in patients:
        r = client.post('/api/v1/consents', headers=admin, json={
            'patient_id': p['id'], 'purpose': 'intake',
            'accepted': True, 'notice_version': 'v1'
        })
        assert r.status_code == 201, r.text
    first_case = client.post('/api/v1/cases', headers=admin, json={
        'patient_id': patients[0]['id'], 'complaint': 'Test referral only',
        'specialty': 'general'
    })
    assert first_case.status_code == 201, first_case.text
    second_case = client.post('/api/v1/cases', headers=admin, json={
        'patient_id': patients[1]['id'], 'complaint': 'Test referral only',
        'specialty': 'general'
    })
    assert second_case.status_code == 409, second_case.text

    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Patient).where(
            Patient.tenant_id == ids[0]
        )) == 2
        assert db.scalar(select(func.count()).select_from(Case).where(
            Case.tenant_id == ids[0]
        )) == 1


def test_production_requires_subscription_without_implicit_unlimited_trial(context, monkeypatch):
    client, auth, _, _ = context
    admin = auth('a')
    monkeypatch.setenv('APP_ENV', 'production')
    response = client.post('/api/v1/patients', headers=admin, json={
        'full_name': 'Synthetic Only', 'language': 'en'
    })
    assert response.status_code == 403, response.text
    assert 'provisioning' in response.json()['detail'].lower()


def test_paid_activations_are_not_exposed_as_self_service(context):
    client, auth, _, _ = context
    admin = auth('a')
    assert client.post('/api/v1/saas/subscription/activate-paid', headers=admin,
        json={'plan_code': 'ENTERPRISE', 'payment_reference': 'synthetic'}).status_code == 404
