"""Security audit trail: denied access and authentication outcomes.

Denied attempts are written and committed immediately, because the request is
about to be aborted and its own transaction would otherwise be rolled back.
Never store passwords, tokens, OTP codes or medical content in ``detail``.
"""
from __future__ import annotations
import hashlib
from sqlalchemy.orm import Session
from .models import Audit

ANONYMOUS = "anonymous"


def fingerprint(value: str) -> str:
    """Stable, non-reversible identifier for an unknown login name (36 chars max)."""
    return "sha256:" + hashlib.sha256(value.strip().lower().encode()).hexdigest()[:29]


def record(db: Session, *, tenant_id: str, event: str, user_id: str | None = None,
           entity_type: str = "User", entity_id: str | None = None, detail: str | None = None,
           commit: bool = True) -> None:
    try:
        db.add(Audit(tenant_id=tenant_id, user_id=user_id or ANONYMOUS, event=event,
                     entity_type=entity_type, entity_id=(entity_id or user_id or ANONYMOUS)[:36],
                     detail=(detail or None) and detail[:300]))
        if commit:
            db.commit()
    except Exception:  # an audit failure must never mask the security decision itself
        db.rollback()
