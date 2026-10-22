"""Tenant-scoped SaaS plan foundation; no payment or paid activation is performed here.

Only patients and cases creation quotas are enforced by the API integration.
Production requests without an explicit subscription fail closed for these actions.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from types import MappingProxyType

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .models import Audit, Case, Patient, Tenant, User, utcnow
from .security import roles

# These are technical limits, not prices or a published commercial offer.
PLANS = MappingProxyType({
    'FREE': {'patients': 100, 'cases': 150, 'users': 2},
    'STARTER': {'patients': 1000, 'cases': 2000, 'users': 5},
    'GROWTH': {'patients': 10000, 'cases': 20000, 'users': 25},
    'ENTERPRISE': {'patients': 100000, 'cases': 200000, 'users': 200},
})
METRICS = {'patients': Patient, 'cases': Case, 'users': User}


class TenantSubscription(Base):
    __tablename__ = 'tenant_subscriptions'

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('tenants.id'), primary_key=True
    )
    plan_code: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='active')
    activated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey('users.id'), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


router = APIRouter(prefix='/api/v1/saas', tags=['saas'])
ADMIN = roles('admin')


def _active(subscription: TenantSubscription) -> bool:
    if subscription.status != 'active':
        return False
    if subscription.expires_at is None:
        return True
    expiry = subscription.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry > datetime.now(timezone.utc)


def _counts(db: Session, tenant_id: str) -> dict[str, int]:
    return {
        metric: int(db.scalar(
            select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        ) or 0)
        for metric, model in METRICS.items()
    }


def enforce_create_quota(db: Session, tenant_id: str, metric: str) -> None:
    """Call inside the same DB transaction as creating a patient/case.

    The tenant row lock serializes concurrent PostgreSQL writers across tables.
    SQLite is for isolated synthetic tests, not concurrent production use.
    """
    if metric not in ('patients', 'cases'):
        raise ValueError('Unsupported create quota')
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None:
        raise HTTPException(403, 'Tenant is unavailable')
    subscription = db.get(TenantSubscription, tenant_id)
    if subscription is None:
        # Preserve the existing alpha development experience, but never
        # silently grant unlimited patient creation to production tenants.
        if os.getenv('APP_ENV') == 'production':
            raise HTTPException(403, 'Tenant provisioning is required')
        return
    if not _active(subscription):
        raise HTTPException(403, 'Tenant subscription inactive or expired')
    limits = PLANS.get(subscription.plan_code)
    if limits is None:
        raise HTTPException(403, 'Unknown subscription plan')
    count = db.scalar(
        select(func.count()).select_from(METRICS[metric]).where(
            METRICS[metric].tenant_id == tenant_id
        )
    )
    if (count or 0) >= limits[metric]:
        raise HTTPException(409, 'Tenant plan resource limit reached')


@router.get('/plans')
def plans(user: User = Depends(ADMIN)):
    # Commercial pricing, eligibility, and contract terms remain unset.
    return [{'code': code, 'limits': dict(limits)} for code, limits in PLANS.items()]


@router.get('/subscription')
def get_subscription(
    db: Session = Depends(get_db), user: User = Depends(ADMIN)
):
    subscription = db.get(TenantSubscription, user.tenant_id)
    if subscription is None:
        return {'status': 'unprovisioned', 'plan_code': None, 'enforced': False}
    return {
        'status': subscription.status,
        'plan_code': subscription.plan_code,
        'active': _active(subscription),
        'enforced': True,
        'created_at': subscription.created_at,
        'expires_at': subscription.expires_at,
    }


@router.post('/subscription/activate-free', status_code=201)
def activate_free(
    db: Session = Depends(get_db), user: User = Depends(ADMIN)
):
    """One-time manual free provisioning. Paid plans require a separate gate."""
    tenant = db.scalar(
        select(Tenant).where(Tenant.id == user.tenant_id).with_for_update()
    )
    if tenant is None:
        raise HTTPException(404, 'Tenant not found')
    if db.get(TenantSubscription, user.tenant_id):
        raise HTTPException(409, 'Subscription already provisioned')
    db.add(TenantSubscription(
        tenant_id=user.tenant_id, plan_code='FREE',
        status='active', activated_by=user.id
    ))
    db.add(Audit(
        tenant_id=user.tenant_id, user_id=user.id,
        event='saas_free_plan_activated',
        entity_type='Tenant', entity_id=user.tenant_id
    ))
    db.commit()
    return {'status': 'active', 'plan_code': 'FREE', 'payment_collected': False}


@router.get('/usage')
def usage(db: Session = Depends(get_db), user: User = Depends(ADMIN)):
    subscription = db.get(TenantSubscription, user.tenant_id)
    counts = _counts(db, user.tenant_id)
    limits = (
        dict(PLANS[subscription.plan_code])
        if subscription is not None and subscription.plan_code in PLANS
        else None
    )
    return {
        'plan_code': subscription.plan_code if subscription else None,
        'active': _active(subscription) if subscription else False,
        'counts': counts,
        'limits': limits,
        'quota_enforcement': ['patients', 'cases'] if subscription else [],
        'billing_integrated': False,
    }
