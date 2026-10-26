"""Section 22: safely publish tenant-localized, nonclinical public information.

Only staff-published CMS pages are public. Bootstrap creates DRAFT templates
requiring independent medical, legal and translation review before publishing.
No patient, contact, clinic credentials, referrals, quotes or provider details.
"""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .enterprise_models import ContentPage, TenantSetting
from .models import Tenant, User, Audit
from .security import roles

router = APIRouter(prefix="/api/v1", tags=["multilingual public website"])
LOCALES = ("fa", "ar", "en")
SLUGS = ("about", "services", "process", "faq", "contact",
         "privacy", "terms", "medical-disclaimer")
LEGAL = ("privacy", "terms", "medical-disclaimer")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CONTENT = {
"fa": {
"about": ("درباره برنامه گردشگری سلامت", "این وب‌سایت نمونه‌ای برای توضیح فرایند هماهنگی اداری درخواست‌های گردشگری سلامت است. ما ارائه‌دهنده تشخیص یا درمان نیستیم. هیچ بیمارستان، پزشک یا ارائه‌دهنده خدماتی بدون بررسی مستقل معرفی یا تضمین نمی‌شود. وضعیت عملیاتی هر همکاری باید جداگانه تأیید شود."),
"services": ("خدمات هماهنگی غیر درمانی", "این پلتفرم می‌تواند برای پیگیری درخواست اولیه، ثبت رضایت، هماهنگی زمان ملاقات، درخواست اطلاعات سفر، اقامت و ترجمه استفاده شود. انجام هر خدمت به ظرفیت واقعی و تأیید انسانی وابسته است. هیچ رزرو، ویزا، نتیجه درمان یا هزینه نهایی از طریق این متن تضمین نمی‌شود."),
"process": ("مراحل درخواست", "۱. ابتدا توضیحات عمومی را بخوانید. ۲. برای تماس، از کانال خصوصی رسمی و تأییدشده استفاده کنید. ۳. قبل از انتقال داده شخصی یا پزشکی باید هویت، رضایت و شرایط قانونی تأیید شوند. ۴. هماهنگ‌کننده انسانی پیگیری را انجام می‌دهد. این صفحه ثبت درخواست زنده نیست."),
"faq": ("پرسش‌های متداول", "آیا درمان تضمین می‌شود؟ خیر. تصمیم‌های پزشکی فقط با متخصص واجد صلاحیت است. آیا قیمت قطعی است؟ خیر، برآورد فقط پس از بررسی انسانی معتبر است. آیا می‌توان مدارک پزشکی ارسال کرد؟ در نسخه آزمایشی خیر؛ مسیر تولید باید پیش از دریافت اطلاعات واقعی تأیید شود."),
"contact": ("ارتباط با هماهنگ‌کننده", "این یک صفحه معرفی آزمایشی است. اطلاعات تماس رسمی پس از تأیید مدیر سازمان منتشر می‌شود. لطفاً در پیام‌های عمومی نام، شماره گذرنامه، تشخیص، گزارش آزمایش یا سایر اطلاعات حساس ارسال نکنید. برای فوریت پزشکی به خدمات اضطراری محلی مراجعه کنید."),
"privacy": ("اطلاعیه حریم خصوصی — پیش‌نویس", "این متن نمونه و نه اطلاعیه قانونی معتبر است. پیش از جمع‌آوری داده واقعی، سازمان باید مسئول پردازش، اهداف، مبنای حقوقی، محل ذخیره، دریافت‌کنندگان، مدت نگهداری، انتقال بین‌المللی، حقوق فرد و راه تماس مسئول حریم خصوصی را با تأیید حقوقی مشخص کند. این سامانه برای داده پزشکی واقعی در تولید تأیید نشده است."),
"terms": ("شرایط استفاده — پیش‌نویس", "این شرایط نمونه، قرارداد الزام‌آور نیست. خدمات توصیف‌شده صرفاً هماهنگی اداری آزمایشی هستند و ارائه واقعی به بررسی مستقل شریک، قوانین کشور مبدأ و مقصد، قیمت، لغو و شرایط شکایت وابسته است. قبل از عرضه عمومی این سند باید به تأیید مشاور حقوقی برسد."),
"medical-disclaimer": ("سلب مسئولیت پزشکی", "این وب‌سایت خدمات فوریت، تشخیص، تجویز، تضمین موفقیت درمان یا نظر تخصصی ارائه نمی‌کند. اطلاعات فقط عمومی و غیرتشخیصی هستند. برای ارزیابی وضعیت خود با پزشک واجد صلاحیت مشورت کنید؛ در موارد اورژانسی از خدمات اضطراری محلی کمک بگیرید."),
},
"ar": {
"about": ("حول منصة السياحة العلاجية", "هذا موقع تجريبي لشرح التنسيق الإداري لطلبات السياحة العلاجية. نحن لا نقدم تشخيصاً أو علاجاً. لا نعتمد أي مستشفى أو طبيب أو شريك إلا بعد تحقق مستقل ومراجعة بشرية. يجب إثبات أي تعاون فعلي بشكل منفصل."),
"services": ("خدمات التنسيق غير الطبي", "يمكن للمنصة متابعة الاستفسارات الأولية والموافقات والمواعيد وطلبات النقل والإقامة والترجمة. تخضع كل خدمة للتوافر الحقيقي والمراجعة البشرية. لا نضمن حجزاً أو تأشيرة أو نتيجة طبية أو سعراً نهائياً."),
"process": ("خطوات الطلب", "١. اقرأ المعلومات العامة أولاً. ٢. استخدم قناة اتصال خاصة ومعتمدة للتواصل. ٣. يجب التحقق من الهوية والموافقة والمتطلبات القانونية قبل إرسال أي بيانات شخصية أو صحية. ٤. يتابع منسق بشري الإجراءات. هذه الصفحة ليست نظام حجز فعلي."),
"faq": ("الأسئلة الشائعة", "هل النتائج الطبية مضمونة؟ لا. القرارات الطبية من اختصاص الأطباء المؤهلين فقط. هل الأسعار نهائية؟ لا، تتطلب مراجعة بشرية. هل يمكن إرسال الملفات الطبية الآن؟ لا في هذه النسخة التجريبية؛ يلزم اعتماد أمني وقانوني قبل معالجة بيانات حقيقية."),
"contact": ("الاتصال بفريق التنسيق", "هذه صفحة معلومات تجريبية. تُنشر معلومات الاتصال الرسمية بعد مراجعة إدارة المؤسسة. لا ترسل بيانات جواز السفر أو تقارير طبية أو تشخيصاً أو معلومات شخصية حساسة عبر النماذج العامة. للطوارئ اتصل بخدمات الإسعاف المحلية."),
"privacy": ("إشعار الخصوصية — مسودة", "هذا نموذج غير معتمد قانونياً. يجب تحديد جهة التحكم بالبيانات وأغراض المعالجة والأساس القانوني ومكان التخزين والمستلمين وفترات الاحتفاظ وحقوق الأفراد والتحويل الدولي وتفاصيل التواصل بعد مراجعة قانونية مستقلة. لا يجوز استخدام هذه البيئة لبيانات مرضى حقيقية."),
"terms": ("شروط الاستخدام — مسودة", "هذا النص التجريبي ليس اتفاقاً قانونياً نافذاً. المعلومات تصف تنسيقاً إدارياً فقط، وتعتمد الخدمات الحقيقية على مراجعة الشركاء والقوانين المحلية والأسعار والإلغاء والشكاوى. يجب اعتماد الشروط قانونياً قبل الإطلاق التجاري."),
"medical-disclaimer": ("إخلاء مسؤولية طبية", "الموقع لا يقدم خدمات طوارئ أو تشخيصاً أو وصفات علاجية أو ضماناً لنتائج العلاج. المعلومات عامة ولا تحل محل استشارة مختص مؤهل. في حالات الطوارئ اطلب المساعدة الطبية المحلية فوراً."),
},
"en": {
"about": ("About the medical travel coordination platform", "This demonstration explains administrative coordination for medical travel inquiries. We do not provide diagnosis or treatment. No clinic, physician or external provider is endorsed or verified through this website; actual partnerships require separate independent human checks."),
"services": ("Nonclinical coordination services", "The platform can help staff track initial inquiries, consent status, appointment requests, accommodation, transport and interpreter coordination. Every service depends on independently verified partner availability and human approval. No visa, appointment, reservation, final price or treatment outcome is guaranteed."),
"process": ("How the inquiry process works", "1. Review the general information. 2. Use an independently confirmed private communication channel. 3. Identity, consent and applicable law must be checked before transmitting any personal or health records. 4. A human coordinator reviews next steps. This informational page does not create a live reservation."),
"faq": ("Frequently asked questions", "Are medical outcomes guaranteed? No. Qualified clinicians make clinical decisions. Are quoted prices final? No; human review is needed. Can I upload real medical files? Not in this alpha environment. Security, legal controls and independently verified identity must be in place before accepting real patient information."),
"contact": ("Contact and assistance", "This is an informational demonstration. Official contact details may be published after organizational verification. Do not put passport numbers, diagnoses, laboratory results or other sensitive information into public messages. For urgent health needs, contact your local emergency services."),
"privacy": ("Privacy notice — draft", "This is a template, not an approved privacy notice. Before any real personal information is collected, the organization must independently validate its controller identity, purposes, legal basis, storage region, processors, retention, cross-border transfer, privacy rights and contact channel. Production handling of real patient data is not approved."),
"terms": ("Terms of use — draft", "This example text is not an enforceable agreement. The site describes internal administrative coordination only. Actual services require independent partner due diligence, local-law assessment, pricing, cancellation and complaint procedures. Counsel must review terms before public commercial launch."),
"medical-disclaimer": ("Medical disclaimer", "This website cannot provide emergency care, diagnosis, prescriptions, specialist medical advice or guaranteed treatment outcomes. Information is general, not clinical guidance. Consult appropriately licensed professionals and contact local emergency services for urgent medical needs."),
},
}

def tenant_by_slug(db:Session,slug:str):
    tenant=db.scalar(select(Tenant).where(Tenant.slug==slug))
    if not tenant:raise HTTPException(404,"Public site not found")
    return tenant

def public_rows(db:Session,tenant_id:str):
    return db.scalars(select(ContentPage).where(
        ContentPage.tenant_id==tenant_id,
        ContentPage.status=="published",
        ContentPage.locale.in_(LOCALES),
        ContentPage.slug.in_(SLUGS),
    ).order_by(ContentPage.slug,ContentPage.locale)).all()

def settings(db:Session,tenant_id:str):
    item=db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id==tenant_id,
        TenantSetting.key=="public_portal"))
    if not item:return {}
    import json
    try:
        parsed=json.loads(item.value_json)
        return parsed if isinstance(parsed,dict) else {}
    except (ValueError,TypeError):
        return {}

@router.get("/public/{tenant_slug}/site-manifest")
def site_manifest(tenant_slug:str,db:Session=Depends(get_db)):
    t=tenant_by_slug(db,tenant_slug)
    rows=public_rows(db,t.id)
    by_slug:dict[str,dict]={}
    for row in rows:
        entry=by_slug.setdefault(row.slug,{"slug":row.slug,"translations":{}})
        entry["translations"][row.locale]={"title":row.title,
            "locale":row.locale,"slug":row.slug,
            "summary":row.body[:155] if row.body else ""}
    configured=settings(db,t.id)
    completeness={loc:sorted(set(SLUGS)-{
        row.slug for row in rows if row.locale==loc}) for loc in LOCALES}
    fully_translated=all(not missing for missing in completeness.values())
    # A tenant must explicitly attest that publication/legal content/SEO rights
    # were reviewed. Such self-attestation is not independent legal clearance.
    opted_in=configured.get("search_indexing_enabled") is True
    legally_reviewed=configured.get("legal_content_reviewed") is True
    indexable=fully_translated and opted_in and legally_reviewed
    return {
        "tenant_slug":t.slug,
        "locales":list(LOCALES),
        "pages":list(by_slug.values()),
        "required_slugs":list(SLUGS),
        "missing_translations":completeness,
        "all_languages_complete":fully_translated,
        "indexing_opt_in":opted_in,
        "legal_review_self_attested":legally_reviewed,
        "search_indexing_allowed":indexable,
        "independent_legal_approval_verified":False,
        "clinical_provider_verified":False,
        "accepts_real_patient_information":False,
        "disclosure":"Administrative demonstration only; no clinical decisions or independently verified providers.",
    }

@router.post("/cms/public-site/bootstrap",status_code=201)
def bootstrap(db:Session=Depends(get_db),user:User=Depends(roles("admin"))):
    """Seed explicit drafts; never auto-publish or change edited CMS pages."""
    existing={(p.slug,p.locale) for p in db.scalars(select(ContentPage).where(
        ContentPage.tenant_id==user.tenant_id)).all()}
    created=[]
    for loc,pages in CONTENT.items():
        for slug,(title,body) in pages.items():
            if (slug,loc) in existing:continue
            row=ContentPage(tenant_id=user.tenant_id,slug=slug,locale=loc,
                title=title,body=body,status="draft")
            db.add(row);db.flush()
            db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,
                event="public_website_template_drafted",
                entity_type="ContentPage",entity_id=row.id))
            created.append({"id":row.id,"slug":slug,"locale":loc})
    db.commit()
    return {"created":len(created),"items":created,
        "published":0,"manual_legal_medical_translation_review_required":True,
        "real_patient_data_allowed":False}

class DraftEdit(BaseModel):
    model_config=ConfigDict(extra="forbid")
    title:str=Field(min_length=2,max_length=250)
    body:str=Field(min_length=1,max_length=30000)

@router.get("/cms/public-site/drafts/{page_id}")
def draft_read(page_id:str,db:Session=Depends(get_db),user:User=Depends(roles("admin"))):
    x=db.scalar(select(ContentPage).where(ContentPage.id==page_id,
        ContentPage.tenant_id==user.tenant_id))
    if not x:raise HTTPException(404,"CMS page not found")
    return {"id":x.id,"slug":x.slug,"locale":x.locale,
        "title":x.title,"body":x.body,"status":x.status}

@router.patch("/cms/public-site/drafts/{page_id}")
def draft_edit(page_id:str,body:DraftEdit,db:Session=Depends(get_db),
               user:User=Depends(roles("admin"))):
    x=db.scalar(select(ContentPage).where(ContentPage.id==page_id,
        ContentPage.tenant_id==user.tenant_id).with_for_update())
    if not x:raise HTTPException(404,"CMS page not found")
    if x.status!="draft":
        raise HTTPException(409,"Unpublish before editing; review translation and legal text again")
    x.title=body.title.strip()
    x.body=body.body.strip()
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="public_website_draft_edited",
        entity_type="ContentPage",entity_id=x.id))
    db.commit()
    return {"id":x.id,"slug":x.slug,"locale":x.locale,"status":x.status,"title":x.title}

@router.patch("/cms/public-site/pages/{page_id}/unpublish")
def unpublish(page_id:str,db:Session=Depends(get_db),
              user:User=Depends(roles("admin"))):
    x=db.scalar(select(ContentPage).where(ContentPage.id==page_id,
        ContentPage.tenant_id==user.tenant_id).with_for_update())
    if not x:raise HTTPException(404,"CMS page not found")
    if x.status!="published":raise HTTPException(409,"Only published pages can be unpublished")
    x.status="draft";x.approved_by=None
    db.add(Audit(tenant_id=user.tenant_id,user_id=user.id,event="public_website_page_unpublished",
        entity_type="ContentPage",entity_id=x.id))
    db.commit()
    return {"id":x.id,"status":"draft","search_indexing_pending_review":True}
