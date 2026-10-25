"""Audited, source-bound administrative quotation revisions.

Only same-currency verified local price records are supported. No inferred FX.
Snapshots are immutable; administrator approval is not provider confirmation.
"""
import json
import re
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import BaseModel,Field
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Quote,Case,Patient,Audit
from .enterprise_models import QuoteVersion,ServicePrice,CaseTimeline
from .security import roles
from .safety_rules import active_consent

router=APIRouter(prefix="/api/v1/quotation-versions",tags=["versioned quotations"])
staff=roles("admin","operator")
admin=roles("admin")
MAX=10**15
REF=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$"

class LineIn(BaseModel):
    price_id:str
    units:int=Field(ge=1,le=100000)

class DraftIn(BaseModel):
    lines:list[LineIn]=Field(min_length=1,max_length=50)

class ReviewIn(BaseModel):
    reference:str=Field(min_length=6,max_length=100,pattern=REF)

def quote_case(db,user,qid,lock=False):
    q=db.scalar(select(Quote).where(Quote.id==qid,Quote.tenant_id==user.tenant_id).with_for_update() if lock else
                select(Quote).where(Quote.id==qid,Quote.tenant_id==user.tenant_id))
    if q is None:raise HTTPException(404,"Quote not found")
    case=db.scalar(select(Case).where(Case.tenant_id==user.tenant_id,Case.id==q.case_id))
    if case is None:raise HTTPException(404,"Case not found")
    p=db.scalar(select(Patient).where(Patient.tenant_id==user.tenant_id,Patient.id==case.patient_id))
    if p is None:raise HTTPException(404,"Patient not found")
    if not active_consent(db,user.tenant_id,p.id,"intake"):raise HTTPException(409,"Active intake consent required")
    return q,case

def payload(x):
    return {"id":x.id,"quote_id":x.quote_id,"version":x.version,
            "status":x.status,"currency":x.currency,"total_minor":x.total_minor,
            "lines":json.loads(x.lines_json),"created_at":x.created_at,
            "approval_reference":x.approval_reference,
            "provider_cost_externally_verified":False,
            "fx_conversion_used":False,"patient_data_included":False}

@router.post("/quotes/{quote_id}/draft",status_code=201)
def draft(quote_id:str,body:DraftIn,db:Session=Depends(get_db),user:User=Depends(staff)):
    q,case=quote_case(db,user,quote_id,lock=True)
    if q.status!="draft":raise HTTPException(409,"Base quote cannot be changed")
    if case.status in ("cancelled","closed"):raise HTTPException(409,"Inactive case")
    if q.amount_minor!=0:
        raise HTTPException(409,"Existing manual quote amount must be reconciled before managed versions")
    versions=db.scalars(select(QuoteVersion).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.quote_id==q.id
    ).order_by(QuoteVersion.version.desc())).all()
    if any(v.status=="approved" for v in versions):raise HTTPException(409,"Approved snapshot is immutable")
    # Explicit revision invalidates old, unapproved revision.
    rows=[];total=0
    for item in body.lines:
        price=db.scalar(select(ServicePrice).where(
            ServicePrice.id==item.price_id,ServicePrice.tenant_id==user.tenant_id,
            ServicePrice.active.is_(True)))
        if price is None:raise HTTPException(404,"Price source not found")
        end=price.valid_until.replace(tzinfo=timezone.utc) if price.valid_until.tzinfo is None else price.valid_until.astimezone(timezone.utc)
        if end<=datetime.now(timezone.utc):raise HTTPException(409,"Expired price source")
        if price.currency!=q.currency:raise HTTPException(409,"Mixed currencies require independently approved FX workflow")
        amount=item.units*price.amount_minor
        total+=amount
        if total>MAX:raise HTTPException(422,"Quote exceeds integer safe limit")
        rows.append({"price_id":price.id,"label":price.label,"service_code":price.service_code,
                     "units":item.units,"unit_amount_minor":price.amount_minor,
                     "line_total_minor":amount,"source_reference":price.source,
                     "valid_until":price.valid_until.isoformat(),
                     "verified_by":price.verified_by})
    if total<=0:raise HTTPException(422,"Positive total required")
    for old in versions:
        if old.status=="draft":old.status="superseded"
    revision=QuoteVersion(tenant_id=user.tenant_id,quote_id=q.id,case_id=case.id,
        version=max((x.version for x in versions),default=0)+1,
        currency=q.currency,lines_json=json.dumps(rows,ensure_ascii=True,separators=(",",":")),
        total_minor=total,status="draft",created_by=user.id)
    db.add(revision);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="quote_revision_drafted",
                 entity_type="QuoteVersion",entity_id=revision.id))
    db.commit()
    return payload(revision)

@router.get("/quotes/{quote_id}")
def list_versions(quote_id:str,db:Session=Depends(get_db),user:User=Depends(staff)):
    q,case=quote_case(db,user,quote_id)
    rows=db.scalars(select(QuoteVersion).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.quote_id==q.id
    ).order_by(QuoteVersion.version.desc()).limit(100)).all()
    return {"items":[payload(x) for x in rows],"verified_provider_quote":False}

@router.post("/versions/{version_id}/approve")
def approve(version_id:str,body:ReviewIn,db:Session=Depends(get_db),user:User=Depends(admin)):
    x=db.scalar(select(QuoteVersion).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.id==version_id).with_for_update())
    if x is None:raise HTTPException(404,"Version not found")
    q,case=quote_case(db,user,x.quote_id,lock=True)
    if x.status!="draft" or q.status!="draft":raise HTTPException(409,"Not approvable")
    latest=db.scalar(select(func.max(QuoteVersion.version)).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.quote_id==q.id))
    if x.version!=latest:raise HTTPException(409,"Only latest revision may be approved")
    lines=json.loads(x.lines_json)
    if sum(i["line_total_minor"] for i in lines)!=x.total_minor:
        raise HTTPException(409,"Financial totals do not reconcile")
    # A price expiring after drafting must trigger a new quote, not stale approval.
    if any(datetime.fromisoformat(i["valid_until"]).astimezone(timezone.utc)<=datetime.now(timezone.utc) for i in lines):
        raise HTTPException(409,"Underlying price has expired")
    x.status="approved";x.reviewed_by=user.id;x.approval_reference=body.reference
    q.amount_minor=x.total_minor;q.approved_by=user.id;q.status="approved"
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="quote_revision_approved",
                 entity_type="QuoteVersion",entity_id=x.id))
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=case.id,actor_id=user.id,
                        event="quote_revision_approved",details="version="+x.id+";internal_only"))
    db.commit()
    return payload(x)

def pdf_bytes(lines):
    # ASCII-only minimalist PDF; no external font, PHI, financial conversion or JS.
    # Keeps PDF output usable on a bare backend container.
    def clean(s):return re.sub(r"[^ -~]","?",str(s)).replace("\\","\\\\").replace("(","\\(").replace(")","\\)")[:105]
    ops=["BT","/F1 11 Tf","45 795 Td","15 TL"]
    for line in lines:
        ops.append("("+clean(line)+") Tj");ops.append("T*")
    ops.append("ET")
    stream="\n".join(ops).encode("ascii")
    objects=[
      b"<< /Type /Catalog /Pages 2 0 R >>",
      b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
      b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
      b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
      b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream",
    ]
    out=bytearray(b"%PDF-1.4\n");offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(out));out.extend(str(i).encode()+b" 0 obj\n"+obj+b"\nendobj\n")
    start=len(out);out.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for pos in offsets[1:]:out.extend(f"{pos:010d} 00000 n \n".encode())
    out.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"+str(start).encode()+b"\n%%EOF")
    return bytes(out)

@router.get("/versions/{version_id}/pdf")
def export_pdf(version_id:str,db:Session=Depends(get_db),user:User=Depends(staff)):
    x=db.scalar(select(QuoteVersion).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.id==version_id))
    if x is None:raise HTTPException(404,"Version not found")
    q,case=quote_case(db,user,x.quote_id)
    if x.status!="approved":raise HTTPException(409,"Only approved snapshots can be exported")
    lines=[
      "MEDTOUR AI - ADMINISTRATIVE QUOTATION",
      "TEST / DEVELOPMENT DATA ONLY - NOT A PROVIDER INVOICE",
      "Quote ID: "+q.id,"Version: "+str(x.version),
      "Currency: "+x.currency,"Case Reference: "+case.id,
      "Internal approval ref: "+str(x.approval_reference),
      "----------------------------------------",
    ]
    for i,row in enumerate(json.loads(x.lines_json),1):
        lines.append(f"{i}. {row['service_code']} / {row['label']}")
        lines.append(f"   {row['units']} x {row['unit_amount_minor']} = {row['line_total_minor']} {x.currency} minor units")
        lines.append("   Source: "+row["source_reference"])
    lines+=["----------------------------------------","TOTAL: "+str(x.total_minor)+" "+x.currency+" minor units",
            "No FX applied; no external hospital/provider confirmation.",
            "Not a clinical recommendation or payment confirmation."]
    if len(lines)>52:raise HTTPException(422,"Document exceeds single-page safety limit")
    return Response(pdf_bytes(lines),media_type="application/pdf",
        headers={"Content-Disposition":'attachment; filename="quotation-'+x.id+'.pdf"',
                 "Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
