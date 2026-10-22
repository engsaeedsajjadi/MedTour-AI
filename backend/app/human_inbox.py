"""Human inbox for synthetic administrative communications only.

No automated medical decisions, real-data authorization, implicit WhatsApp
send or live Chatwoot synchronization. All writes are scoped to tenant,
patient consent, channel, and assigned operator.
"""
from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, Patient, Conversation, Message, Audit
from .enterprise_models import InboxThread, InboxAction
from .security import roles
from .safety_rules import active_consent
from .intake import LANGUAGES

router = APIRouter(prefix="/api/v1/inbox", tags=["human inbox"])
staff = roles("admin", "operator")
REF = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"
STATUSES = frozenset({"open", "assigned", "waiting", "resolved"})


def require_thread(db: Session, user: User, conversation_id: str,
                   *, lock: bool = False, consent: bool = True):
    query = select(Conversation).where(
        Conversation.tenant_id == user.tenant_id,
        Conversation.id == conversation_id,
    )
    c = db.scalar(query.with_for_update() if lock else query)
    if c is None:
        raise HTTPException(404, "Conversation not found")
    patient = db.scalar(select(Patient).where(
        Patient.tenant_id == user.tenant_id, Patient.id == c.patient_id,
    ))
    if patient is None:
        raise HTTPException(404, "Patient not found")
    if consent and not active_consent(db, user.tenant_id, patient.id, "communication"):
        raise HTTPException(409, "Active communication consent required")
    if user.role != "admin" and c.assigned_user_id not in (None, user.id):
        raise HTTPException(403, "Conversation assigned to another operator")
    thread = db.scalar(select(InboxThread).where(
        InboxThread.tenant_id == user.tenant_id,
        InboxThread.conversation_id == c.id,
        InboxThread.patient_id == c.patient_id,
    ))
    return c, thread


def ensure_thread(db: Session, c: Conversation) -> InboxThread:
    # Callers lock the Conversation row before creating the inbox state.
    thread = db.scalar(select(InboxThread).where(
        InboxThread.tenant_id == c.tenant_id,
        InboxThread.conversation_id == c.id,
        InboxThread.patient_id == c.patient_id,
    ))
    if thread is None:
        thread = InboxThread(
            tenant_id=c.tenant_id, conversation_id=c.id,
            patient_id=c.patient_id,
            status="assigned" if c.assigned_user_id else "open",
            priority="normal",
        )
        db.add(thread)
        db.flush()
    return thread


def record(db: Session, c: Conversation, actor: User | None,
           action: str, old: str, new: str, target_id: str | None = None,
           reference: str | None = None):
    db.add(InboxAction(
        tenant_id=c.tenant_id, conversation_id=c.id,
        actor_user_id=actor.id if actor else None, action=action,
        reference=reference,
        from_status=old, to_status=new, target_user_id=target_id,
    ))
    if actor:
        db.add(Audit(
            tenant_id=c.tenant_id, user_id=actor.id,
            event="inbox_" + action,
            entity_type="Conversation", entity_id=c.id,
        ))


def inbound_webchat(db: Session, c: Conversation, *, urgent: bool = False) -> None:
    """Called in patient portal transaction; does not commit or send externally."""
    # New patient activity reopens a completed thread, never turns AI back on.
    db.scalar(select(Conversation.id).where(
        Conversation.id == c.id, Conversation.tenant_id == c.tenant_id,
    ).with_for_update())
    thread = ensure_thread(db, c)
    before = thread.status
    if before in ("resolved", "waiting"):
        thread.status = "assigned" if c.assigned_user_id else "open"
        c.human_handoff = True
    if urgent:
        thread.priority = "urgent"
        c.human_handoff = True
    if urgent or thread.status != before:
        record(db, c, None,
               "urgent_keyword_alert" if urgent else "patient_reopened",
               before, thread.status)


def thread_view(c: Conversation, t: InboxThread | None, patient_language: str) -> dict:
    return {
        "conversation_id": c.id, "patient_id": c.patient_id,
        "channel": c.channel, "language": patient_language,
        "status": t.status if t else ("assigned" if c.assigned_user_id else "open"),
        "priority": t.priority if t else "normal",
        "assigned_user_id": c.assigned_user_id,
        "human_handoff": c.human_handoff,
        "created_at": c.created_at,
        "external_sends": False, "clinical_decisions": False,
    }


@router.get("/readiness")
def readiness(user: User = Depends(staff)):
    return {
        "internal_webchat_available": True,
        "whatsapp_human_approval_queue_available": True,
        "live_whatsapp_send_verified": False,
        "chatwoot_sync_configured": False,
        "chatwoot_sync_live_verified": False,
        "automatic_clinical_message_allowed": False,
        "real_patient_data_allowed": False,
        "message_delivery_reliability_tested_with_live_provider": False,
    }


@router.get("/threads")
def list_threads(
    status: Literal["open", "assigned", "waiting", "resolved"] | None = None,
    assigned: Literal["mine", "unassigned", "all"] = "all",
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(staff),
):
    query = select(Conversation).where(Conversation.tenant_id == user.tenant_id)
    if user.role != "admin":
        query = query.where(
            (Conversation.assigned_user_id == user.id) |
            Conversation.assigned_user_id.is_(None)
        )
    if assigned == "mine":
        query = query.where(Conversation.assigned_user_id == user.id)
    elif assigned == "unassigned":
        query = query.where(Conversation.assigned_user_id.is_(None))
    conversations = db.scalars(query.order_by(
        Conversation.created_at.desc(), Conversation.id.desc()
    ).limit(300)).all()
    results = []
    for c in conversations:
        if not active_consent(db, user.tenant_id, c.patient_id, "communication"):
            continue
        patient = db.scalar(select(Patient).where(
            Patient.tenant_id == user.tenant_id, Patient.id == c.patient_id,
        ))
        if patient is None:
            continue
        row = db.scalar(select(InboxThread).where(
            InboxThread.tenant_id == user.tenant_id,
            InboxThread.conversation_id == c.id,
            InboxThread.patient_id == patient.id,
        ))
        current_status = row.status if row else ("assigned" if c.assigned_user_id else "open")
        if status and current_status != status:
            continue
        results.append(thread_view(c, row, patient.language))
        if len(results) >= limit:
            break
    priority = {"urgent": 0, "high": 1, "normal": 2}
    results.sort(key=lambda x: (
        priority.get(x["priority"], 2), x["created_at"], x["conversation_id"]
    ))
    return {"items": results, "scan_bounded": True,
            "medical_content_included": False, "automatic_send": False}


class AssignmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_user_id: str


def assign(db: Session, c: Conversation, thread: InboxThread,
           user: User, target: User | None, action: str):
    before = thread.status
    if thread.status == "resolved":
        raise HTTPException(409, "Resolved conversation requires explicit reopen")
    c.assigned_user_id = target.id if target else None
    c.human_handoff = True
    thread.status = "assigned" if target else "open"
    record(db, c, user, action, before, thread.status, c.assigned_user_id)
    db.commit()
    return {"conversation_id": c.id, "status": thread.status,
            "assigned_user_id": c.assigned_user_id, "human_handoff": True}


@router.post("/threads/{conversation_id}/claim")
def claim(conversation_id: str, db: Session = Depends(get_db),
          user: User = Depends(staff)):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    if c.assigned_user_id and c.assigned_user_id != user.id:
        raise HTTPException(409, "Already assigned to another operator")
    thread = thread or ensure_thread(db, c)
    if c.assigned_user_id == user.id and thread.status == "assigned":
        return {"conversation_id": c.id, "status": thread.status,
                "assigned_user_id": user.id, "reused": True}
    target = db.scalar(select(User).where(
        User.id == user.id, User.tenant_id == user.tenant_id,
        User.active.is_(True), User.role.in_(("admin", "operator")),
    ))
    response = assign(db, c, thread, user, target, "claimed")
    return {**response, "reused": False}


@router.post("/threads/{conversation_id}/assign")
def admin_assign(conversation_id: str, body: AssignmentIn,
                 db: Session = Depends(get_db),
                 user: User = Depends(roles("admin"))):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    target = db.scalar(select(User).where(
        User.id == body.assigned_user_id,
        User.tenant_id == user.tenant_id,
        User.active.is_(True), User.role.in_(("admin", "operator")),
    ))
    if target is None:
        raise HTTPException(404, "Active coordinator not found")
    thread = thread or ensure_thread(db, c)
    if c.assigned_user_id == target.id and thread.status == "assigned":
        return {"conversation_id": c.id, "status": thread.status,
                "assigned_user_id": target.id, "reused": True}
    response = assign(db, c, thread, user, target, "reassigned")
    return {**response, "reused": False}


@router.post("/threads/{conversation_id}/release")
def release(conversation_id: str, db: Session = Depends(get_db),
            user: User = Depends(staff)):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    if not c.assigned_user_id:
        raise HTTPException(409, "Conversation has no current owner")
    if user.role != "admin" and c.assigned_user_id != user.id:
        raise HTTPException(403, "Only owner or administrator can release")
    return assign(db, c, thread or ensure_thread(db, c),
                  user, None, "released")


class StateChangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=6, max_length=100,
                           pattern=REF)


@router.post("/threads/{conversation_id}/resolve")
def resolve(conversation_id: str, body: StateChangeIn,
            db: Session = Depends(get_db),
            user: User = Depends(staff)):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    thread = thread or ensure_thread(db, c)
    if thread.status == "resolved":
        raise HTTPException(409, "Already resolved")
    if user.role != "admin" and c.assigned_user_id != user.id:
        raise HTTPException(403, "Only assigned operator can resolve")
    before = thread.status
    thread.status = "resolved"
    c.human_handoff = True  # Never auto-reactivate bot after staff closure.
    record(db, c, user, "resolved", before, thread.status, reference=body.reference)
    db.commit()
    return {"conversation_id": c.id, "status": thread.status,
            "resolution_reference_recorded": True,
            "external_delivery_confirmed": False, "bot_reactivated": False}


@router.post("/threads/{conversation_id}/reopen")
def reopen(conversation_id: str, body: StateChangeIn,
           db: Session = Depends(get_db), user: User = Depends(staff)):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    thread = thread or ensure_thread(db, c)
    if thread.status != "resolved":
        raise HTTPException(409, "Only resolved conversations can reopen")
    if user.role != "admin" and c.assigned_user_id != user.id:
        raise HTTPException(403, "Only assigned operator can reopen")
    before = thread.status
    thread.status = "assigned" if c.assigned_user_id else "open"
    c.human_handoff = True
    record(db, c, user, "reopened", before, thread.status, reference=body.reference)
    db.commit()
    return {"conversation_id": c.id, "status": thread.status, "bot_reactivated": False}


@router.get("/threads/{conversation_id}/events")
def events(conversation_id: str, db: Session = Depends(get_db),
           user: User = Depends(staff)):
    c, _ = require_thread(db, user, conversation_id)
    rows = db.scalars(select(InboxAction).where(
        InboxAction.tenant_id == user.tenant_id,
        InboxAction.conversation_id == c.id,
    ).order_by(InboxAction.created_at.desc()).limit(100)).all()
    return {
        "items": [{"action": r.action, "reference": r.reference, "from_status": r.from_status,
                   "to_status": r.to_status, "created_at": r.created_at,
                   "actor_user_id": r.actor_user_id}
                  for r in rows],
        "message_contents_included": False,
    }


@router.get("/threads/{conversation_id}/messages")
def messages(conversation_id: str,
             limit: int = Query(100, ge=1, le=200),
             db: Session = Depends(get_db),
             user: User = Depends(staff)):
    c, _ = require_thread(db, user, conversation_id)
    rows = db.scalars(select(Message).where(
        Message.tenant_id == user.tenant_id,
        Message.conversation_id == c.id,
    ).order_by(Message.created_at.desc(), Message.id.desc())
                     .limit(limit)).all()
    return [{"id": r.id, "sender": r.sender, "language": r.language,
             "body": r.body, "created_at": r.created_at} for r in reversed(rows)]


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)
    language: Literal["fa","ar","en","ps","prs"]


@router.post("/threads/{conversation_id}/reply", status_code=201)
def reply(conversation_id: str, body: ReplyIn,
          db: Session = Depends(get_db), user: User = Depends(staff)):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    if c.channel != "webchat":
        raise HTTPException(409, "No free-form WhatsApp/SMS sends: approved template workflow only")
    if not body.body.strip():
        raise HTTPException(422, "Blank reply")
    if user.role != "admin" and c.assigned_user_id != user.id:
        raise HTTPException(403, "Claim the conversation before replying")
    thread = thread or ensure_thread(db, c)
    if thread.status == "resolved":
        raise HTTPException(409, "Reopen conversation before reply")
    row = Message(
        tenant_id=user.tenant_id, conversation_id=c.id,
        sender="operator", body=body.body, language=body.language,
    )
    db.add(row)
    db.flush()
    c.human_handoff = True
    if thread.status == "open" and c.assigned_user_id:
        thread.status = "assigned"
    record(db, c, user, "staff_replied", thread.status, thread.status)
    db.commit()
    return {"id": row.id, "channel": c.channel, "stored_in_portal": True,
            "external_provider_sent": False, "clinical_validation": False}

@router.post("/threads/{conversation_id}/wait")
def mark_waiting(conversation_id: str, body: StateChangeIn,
                 db: Session = Depends(get_db),
                 user: User = Depends(staff)):
    c, thread = require_thread(db, user, conversation_id, lock=True)
    thread = thread or ensure_thread(db, c)
    if thread.status in ("waiting", "resolved"):
        raise HTTPException(409, "Conversation is already waiting or resolved")
    if user.role != "admin" and c.assigned_user_id != user.id:
        raise HTTPException(403, "Only assigned operator may defer")
    old = thread.status
    thread.status = "waiting"
    c.human_handoff = True
    record(db, c, user, "waiting", old, thread.status, reference=body.reference)
    db.commit()
    return {"conversation_id": c.id, "status": thread.status, "bot_reactivated": False}
