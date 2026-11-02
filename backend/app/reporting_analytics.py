"""Section 31: tenant-scoped, aggregate-only operational reporting.

No row-level patient data, no cohort inference, no real-time bank/provider claims.
"""
from __future__ import annotations
import csv
import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Patient,Case,Appointment,Quote,Task
from .enterprise_models import MoneyEntry,Operation
from .security import roles

router=APIRouter(prefix="/api/v1/analytics",tags=["aggregate reporting"])
ADMIN=roles("admin")

def _group(db,model,tenant_id,column):
    rows=db.execute(select(column,func.count()).where(model.tenant_id==tenant_id)
                    .group_by(column)).all()
    return {str(key or "unspecified"):int(n) for key,n in rows}

@router.get("/overview")
def overview(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    tid=user.tenant_id
    def count(model):
        return int(db.scalar(select(func.count()).select_from(model).where(model.tenant_id==tid)) or 0)
    return {"patients":count(Patient),"cases":count(Case),
            "appointments":count(Appointment),"quotes":count(Quote),"tasks":count(Task),
            "case_status_counts":_group(db,Case,tid,Case.status),
            "appointment_status_counts":_group(db,Appointment,tid,Appointment.status),
            "task_status_counts":_group(db,Task,tid,Task.status),
            "operation_status_counts":_group(db,Operation,tid,Operation.status),
            "payment_entry_counts":_group(db,MoneyEntry,tid,MoneyEntry.entry_type),
            "source":"tenant_database_aggregate","includes_phi":False,
            "financial_settlement_confirmed":False}

@router.get("/overview.csv")
def overview_csv(db:Session=Depends(get_db),user:User=Depends(ADMIN)):
    report=overview(db,user)
    stream=io.StringIO(newline="")
    writer=csv.writer(stream,lineterminator="\r\n")
    writer.writerow(("metric","category","count"))
    for key in ("patients","cases","appointments","quotes","tasks"):
        writer.writerow((key,"total",report[key]))
    for key in ("case_status_counts","appointment_status_counts","task_status_counts",
                "operation_status_counts","payment_entry_counts"):
        for category,n in sorted(report[key].items()):
            # Status values originate in DB. Never allow CSV formula injection.
            safe=str(category)
            if safe.lstrip().startswith(("=","+","-","@","\t","\r")):
                safe="'"+safe
            writer.writerow((key,safe,n))
    return Response(content=stream.getvalue(),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":'attachment; filename="medtour-aggregates.csv"',
                 "Cache-Control":"no-store, private","X-Content-Type-Options":"nosniff"})
