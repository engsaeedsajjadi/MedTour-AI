"""Section 29: read-only, per-currency financial reconciliation for verified manual entries.

These reports NEVER assert processor settlement, issue invoices, accept payments,
apply FX rates or determine a patient's treatment eligibility.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Case, Quote, User
from .enterprise_models import MoneyEntry
from .security import roles

router=APIRouter(prefix="/api/v1/finance",tags=["manual finance reconciliation"])
ADMIN=roles("admin")
TYPES=("payment_received","refund_issued","service_expense")

def _entries(db:Session,tenant_id:str,case_id:str|None,limit:int):
    q=select(MoneyEntry).where(MoneyEntry.tenant_id==tenant_id)
    if case_id:q=q.where(MoneyEntry.case_id==case_id)
    return list(db.scalars(q.order_by(MoneyEntry.created_at.desc(),MoneyEntry.id.desc()).limit(limit)).all())

@router.get("/reconciliation")
def reconciliation(case_id:str|None=None,limit:int=Query(500,ge=1,le=2000),
                   db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if case_id and not db.scalar(select(Case.id).where(
        Case.id==case_id,Case.tenant_id==user.tenant_id)):
        raise HTTPException(404,"Case not found")
    # A bounded report MUST NOT disguise a partial page as a complete ledger.
    entries=_entries(db,user.tenant_id,case_id,limit+1)
    if len(entries)>limit:
        raise HTTPException(409,"Reconciliation exceeds bounded report size; use a reviewed export")
    buckets={}
    for entry in entries:
        if entry.entry_type not in TYPES:
            # Deprecated or legally restricted agency fees cannot appear in balance.
            continue
        bucket=buckets.setdefault(entry.currency,{"currency":entry.currency,
            "received_minor":0,"refunded_minor":0,"expenses_minor":0,"count":0})
        if entry.entry_type=="payment_received":bucket["received_minor"]+=entry.amount_minor
        elif entry.entry_type=="refund_issued":bucket["refunded_minor"]+=entry.amount_minor
        elif entry.entry_type=="service_expense":bucket["expenses_minor"]+=entry.amount_minor
        bucket["count"]+=1
    for b in buckets.values():
        b["net_received_minor"]=b["received_minor"]-b["refunded_minor"]
        b["net_after_expenses_minor"]=b["net_received_minor"]-b["expenses_minor"]
    return {"case_id":case_id,"currencies":sorted(buckets.values(),key=lambda b:b["currency"]),
            "source":"admin_verified_manual_entries","complete_within_limit":True,
            "processor_settlement_verified":False,"accounting_statement":False,
            "cross_currency_total":None}

@router.get("/cases/{case_id}/quote-comparison")
def quote_comparison(case_id:str,db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    if not db.scalar(select(Case.id).where(Case.id==case_id,
                                           Case.tenant_id==user.tenant_id)):
        raise HTTPException(404,"Case not found")
    quotes=list(db.scalars(select(Quote).where(Quote.tenant_id==user.tenant_id,
             Quote.case_id==case_id).order_by(Quote.created_at.desc(),Quote.id.desc()).limit(101)).all())
    if len(quotes)>100:raise HTTPException(409,"Quote history exceeds report limit")
    # A quote is an offer, NOT a posted receivable or verified payment.
    return {"case_id":case_id,"quotes":[{"id":q.id,"currency":q.currency,
        "amount_minor":q.amount_minor,"status":q.status} for q in quotes],
        "outstanding_balance_authoritative":False,"automatic_debt_collection":False,
        "booking_or_treatment_confirmation":False}
