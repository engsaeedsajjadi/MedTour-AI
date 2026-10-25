"""Audited, source-bound administrative quotation revisions.

Only same-currency verified local price records are supported. No inferred FX.
Snapshots are immutable; administrator approval is not provider confirmation.
"""
import json
import re
from io import BytesIO
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from xml.sax.saxutils import escape
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import BaseModel,Field
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .database import get_db
from .models import User,Quote,Case,Patient,Audit
from .enterprise_models import QuoteVersion,ServicePrice,CaseTimeline,VerifiedFxRate
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
    fx_rate_id:str|None=None

class DraftIn(BaseModel):
    lines:list[LineIn]=Field(min_length=1,max_length=50)


class FxRateIn(BaseModel):
    source_currency:str=Field(pattern=r"^[A-Z]{3}$")
    target_currency:str=Field(pattern=r"^[A-Z]{3}$")
    numerator:int=Field(ge=1,le=10**12)
    denominator:int=Field(ge=1,le=10**12)
    source_reference:str=Field(min_length=6,max_length=180,pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{5,179}$")
    expires_at:datetime

@router.post("/fx-rates",status_code=201)
def create_fx_rate(body:FxRateIn,db:Session=Depends(get_db),user:User=Depends(admin)):
    if body.source_currency==body.target_currency:
        raise HTTPException(422,"Same-currency FX conversion is not needed")
    if body.expires_at.tzinfo is None:
        raise HTTPException(422,"Timezone offset required")
    expiry=body.expires_at.astimezone(timezone.utc)
    if not datetime.now(timezone.utc)<expiry<=datetime.now(timezone.utc)+timedelta(days=30):
        raise HTTPException(422,"FX rate expires within 30 days")
    rate=VerifiedFxRate(tenant_id=user.tenant_id,
        source_currency=body.source_currency,target_currency=body.target_currency,
        numerator=body.numerator,denominator=body.denominator,
        source_reference=body.source_reference,expires_at=expiry,
        reviewed_by=user.id,active=True)
    db.add(rate);db.flush()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
                 event="manual_fx_rate_attested",entity_type="VerifiedFxRate",entity_id=rate.id))
    db.commit()
    return {"id":rate.id,"source_currency":rate.source_currency,"target_currency":rate.target_currency,
            "numerator":rate.numerator,"denominator":rate.denominator,
            "expires_at":rate.expires_at,"source_reference":rate.source_reference,
            "live_fx_verified":False,"externally_confirmed":False}

@router.get("/fx-rates")
def list_fx_rates(db:Session=Depends(get_db),user:User=Depends(staff)):
    rows=db.scalars(select(VerifiedFxRate).where(
        VerifiedFxRate.tenant_id==user.tenant_id,VerifiedFxRate.active.is_(True)
    ).order_by(VerifiedFxRate.expires_at.desc()).limit(100)).all()
    now=datetime.now(timezone.utc)
    return {"items":[{"id":r.id,"source_currency":r.source_currency,
        "target_currency":r.target_currency,"numerator":r.numerator,
        "denominator":r.denominator,"source_reference":r.source_reference,
        "expires_at":r.expires_at,"active":r.active}
        for r in rows if utc_time(r.expires_at)>now],
        "provider_fx_live_verified":False}

@router.post("/fx-rates/{rate_id}/revoke")
def revoke_fx_rate(rate_id:str,db:Session=Depends(get_db),user:User=Depends(admin)):
    rate=db.scalar(select(VerifiedFxRate).where(
        VerifiedFxRate.tenant_id==user.tenant_id,VerifiedFxRate.id==rate_id).with_for_update())
    if rate is None:raise HTTPException(404,"FX rate not found")
    if rate.active:
        rate.active=False
        db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
                     event="manual_fx_rate_revoked",entity_type="VerifiedFxRate",entity_id=rate.id))
        db.commit()
    return {"id":rate.id,"active":False}

def utc_time(value:datetime)->datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def convert_half_up(amount:int,numerator:int,denominator:int)->int:
    # Integer-only half-up rounding, conversion applies to the full line.
    return (amount*numerator*2+denominator)//(denominator*2)

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
            "fx_conversion_used":any(y.get("fx_rate_id") for y in json.loads(x.lines_json)),"patient_data_included":False}

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
        original=item.units*price.amount_minor
        fx_id=None
        fx_source=None
        fx_expiry=None
        fx_fraction=None
        if price.currency==q.currency:
            if item.fx_rate_id:raise HTTPException(422,"Do not specify an FX rate for same currency")
            amount=original
        else:
            if not item.fx_rate_id:raise HTTPException(409,"Manual sourced FX approval required")
            rate=db.scalar(select(VerifiedFxRate).where(
                VerifiedFxRate.id==item.fx_rate_id,
                VerifiedFxRate.tenant_id==user.tenant_id,
                VerifiedFxRate.active.is_(True)))
            if rate is None:raise HTTPException(404,"FX source not found")
            if rate.source_currency!=price.currency or rate.target_currency!=q.currency:
                raise HTTPException(409,"FX pair does not match source price and quotation currency")
            if utc_time(rate.expires_at)<=datetime.now(timezone.utc):
                raise HTTPException(409,"FX source expired")
            amount=convert_half_up(original,rate.numerator,rate.denominator)
            fx_id=rate.id
            fx_source=rate.source_reference
            fx_expiry=rate.expires_at.isoformat()
            fx_fraction={"numerator":rate.numerator,"denominator":rate.denominator}
        total+=amount
        if total>MAX:raise HTTPException(422,"Quote exceeds integer safe limit")
        rows.append({"price_id":price.id,"label":price.label,"service_code":price.service_code,
                     "units":item.units,"unit_amount_minor":price.amount_minor,
                     "source_currency":price.currency,"source_total_minor":original,
                     "line_total_minor":amount,"source_reference":price.source,
                     "valid_until":price.valid_until.isoformat(),
                     "fx_rate_id":fx_id,"fx_source_reference":fx_source,
                     "fx_expires_at":fx_expiry,"fx_fraction":fx_fraction,
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
    # Match draft lock order: Quote first, then QuoteVersion.
    existing=db.scalar(select(QuoteVersion).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.id==version_id))
    if existing is None:raise HTTPException(404,"Version not found")
    q,case=quote_case(db,user,existing.quote_id,lock=True)
    x=db.scalar(select(QuoteVersion).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.id==version_id).with_for_update())
    if x.status!="draft" or q.status!="draft":raise HTTPException(409,"Not approvable")
    latest=db.scalar(select(func.max(QuoteVersion.version)).where(
        QuoteVersion.tenant_id==user.tenant_id,QuoteVersion.quote_id==q.id))
    if x.version!=latest:raise HTTPException(409,"Only latest revision may be approved")
    lines=json.loads(x.lines_json)
    if sum(i["line_total_minor"] for i in lines)!=x.total_minor:
        raise HTTPException(409,"Financial totals do not reconcile")
    # A price expiring after drafting must trigger a new quote, not stale approval.
    if any(utc_time(datetime.fromisoformat(i["valid_until"]))<=datetime.now(timezone.utc) for i in lines):
        raise HTTPException(409,"Underlying price has expired")
    for item in lines:
        source=db.scalar(select(ServicePrice).where(
            ServicePrice.tenant_id==user.tenant_id,
            ServicePrice.id==item["price_id"],ServicePrice.active.is_(True)))
        if source is None or source.currency!=item.get("source_currency",x.currency):
            raise HTTPException(409,"Underlying price source unavailable or changed")
        if item.get("fx_rate_id"):
            rate=db.scalar(select(VerifiedFxRate).where(
                VerifiedFxRate.tenant_id==user.tenant_id,
                VerifiedFxRate.id==item["fx_rate_id"],VerifiedFxRate.active.is_(True)))
            if (rate is None or utc_time(rate.expires_at)<=datetime.now(timezone.utc)
                or rate.source_currency!=item["source_currency"] or rate.target_currency!=x.currency
                or rate.numerator!=item["fx_fraction"]["numerator"]
                or rate.denominator!=item["fx_fraction"]["denominator"]):
                raise HTTPException(409,"Manual FX evidence revoked, expired or changed")
    x.status="approved";x.reviewed_by=user.id;x.approval_reference=body.reference
    q.amount_minor=x.total_minor;q.approved_by=user.id;q.status="approved"
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="quote_revision_approved",
                 entity_type="QuoteVersion",entity_id=x.id))
    db.add(CaseTimeline(tenant_id=user.tenant_id,case_id=case.id,actor_id=user.id,
                        event="quote_revision_approved",details="version="+x.id+";internal_only"))
    db.commit()
    return payload(x)

def pdf_bytes(lines):
    """Multi-page, text-sanitized A4 PDF with bounded wrapping and no medical notes."""
    buffer=BytesIO()
    document=SimpleDocTemplate(buffer,pagesize=A4,topMargin=48,bottomMargin=48,
                                leftMargin=42,rightMargin=42,
                                title="MedTour administrative quotation (test only)")
    styles=getSampleStyleSheet()
    normal=ParagraphStyle("SafeQuoteBody",parent=styles["BodyText"],fontName="Helvetica",
        fontSize=9,leading=13,spaceAfter=7)
    header=ParagraphStyle("SafeQuoteHeader",parent=styles["Heading1"],fontName="Helvetica-Bold",
        fontSize=15,leading=21,textColor=colors.HexColor("#17314d"),spaceAfter=16)
    story=[Paragraph("MEDTOUR AI - ADMINISTRATIVE QUOTATION",header)]
    for i,line in enumerate(lines):
        if i == 0:continue
        # ASCII transliteration here remains deliberately conservative:
        # no private font files or unsupported clinical content in this document.
        visible=re.sub(r"[^\x20-\x7E]","?",str(line))
        safe=escape(visible)
        story.append(Paragraph(safe,normal))
    def footer(canvas,doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d7e1ea"))
        canvas.line(42,38,A4[0]-42,38)
        canvas.setFont("Helvetica",8)
        canvas.drawString(42,27,"INTERNAL TEST ESTIMATE - NOT A HOSPITAL INVOICE")
        canvas.drawRightString(A4[0]-42,27,f"Page {doc.page}")
        canvas.restoreState()
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()

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
        if row.get("fx_rate_id"):
            lines.append("   Manual FX reference: "+row["fx_source_reference"])
            lines.append("   Source amount: "+str(row["source_total_minor"])+" "+row["source_currency"]+" minor units")
    lines+=["----------------------------------------","TOTAL: "+str(x.total_minor)+" "+x.currency+" minor units",
            "Documented manual FX only when listed; no live-provider confirmation.",
            "Not a clinical recommendation or payment confirmation."]
    if len(lines)>200:raise HTTPException(422,"Document exceeds bounded export limit")
    return Response(pdf_bytes(lines),media_type="application/pdf",
        headers={"Content-Disposition":'attachment; filename="quotation-'+x.id+'.pdf"',
                 "Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
