"""Non-diagnostic, deterministic five-language administrative receptionist.

No provider calls, patient identifiers, or clinical AI. Message matching is
only for administrative routing; NOT emergency triage or linguistic validation.
All clinically significant communication needs qualified human review.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Literal

from .intake import LANGUAGES, intake_response, normalize_safety_text
from .models import User
from .security import roles

Locale = Literal["fa", "ar", "en", "ps", "prs"]
Intent = Literal["greeting", "appointment", "quote", "documents", "visa", "human", "general"]
router = APIRouter(prefix="/api/v1/receptionist", tags=["multilingual receptionist"])
staff = roles("admin", "operator")

LABELS = {
    "fa": "فارسی", "ar": "العربية", "en": "English",
    "ps": "پښتو", "prs": "دری",
}
DIRECTION = {lang: ("ltr" if lang == "en" else "rtl") for lang in LANGUAGES}

# All text is static and must be independently vetted by native speakers
# and clinical/privacy counsel prior to a real patient-facing launch.
RESPONSES = {
 "fa": {
  "greeting": "سلام. برای هماهنگی اداری خدمات درمانی می‌توانم راهنمایی کنم. لطفاً درخواستتان را مطرح کنید؛ تصمیم‌های پزشکی با متخصص است.",
  "appointment": "برای درخواست نوبت، هماهنگ‌کننده انسانی باید ظرفیت و تأیید پزشک یا مرکز را بررسی کند. در این پیام نوبتی رزرو نشده است.",
  "quote": "هزینه درمان فقط پس از بررسی تیم مسئول و پیش‌فاکتور تأییدشده اعلام می‌شود. این گفتگو قیمت قطعی ارائه نمی‌کند.",
  "documents": "برای مدارک پزشکی از بخش بارگذاری امن پرتال و فقط پس از رضایت استفاده کنید. مدارک را در پیام‌رسان عمومی نفرستید.",
  "visa": "برای ویزا و سفر، اپراتور مدارک و شرایط را با منابع رسمی بررسی می‌کند. صدور ویزا تضمین یا تأیید نشده است.",
  "human": "درخواست ارتباط با هماهنگ‌کننده انسانی ثبت شد. این گفتگو خدمات اورژانسی ارائه نمی‌کند.",
  "general": "لطفاً نوع خدمت یا درخواست اداری خود را بفرمایید. برای مسائل پزشکی، بررسی انسانی ضروری است.",
 },
 "ar": {
  "greeting": "مرحبًا. يمكنني المساعدة في التنسيق الإداري للسفر العلاجي. القرارات الطبية يتخذها المختصون.",
  "appointment": "يجب أن يراجع المنسق البشري المواعيد وتأكيد الطبيب أو المركز. لم يتم حجز أي موعد في هذه المحادثة.",
  "quote": "تُقدَّم الأسعار فقط بعد المراجعة البشرية والموافقة على عرض التكلفة. لا يوجد سعر نهائي هنا.",
  "documents": "أرسل الوثائق الطبية عبر بوابة المستندات الآمنة بعد الموافقة. لا ترسلها في تطبيق مراسلة عام.",
  "visa": "سيتحقق الموظف من متطلبات التأشيرة والسفر عبر المصادر الرسمية. لم تُصدر أو تُضمن أي تأشيرة.",
  "human": "تم تحويل طلب التواصل إلى منسق بشري. هذه ليست خدمة طوارئ.",
  "general": "يرجى توضيح طلب التنسيق الإداري. المسائل الطبية تتطلب مراجعة بشرية.",
 },
 "en": {
  "greeting": "Hello. I can help with administrative coordination for medical travel. Medical decisions require qualified professionals.",
  "appointment": "A human coordinator must check availability and provider confirmation. No appointment has been booked in this chat.",
  "quote": "Costs require human review and an approved quotation. This chat cannot give a final treatment price.",
  "documents": "Use the secure document portal with your consent for medical records. Do not send records through public messaging.",
  "visa": "An operator must check visa and travel requirements with official sources. No visa has been issued or guaranteed.",
  "human": "Your request for a human coordinator has been recorded. This is not an emergency service.",
  "general": "Please describe the administrative service you need. Clinical questions require qualified human review.",
 },
 "ps": {
  "greeting": "سلام. زه د طبي سفر په اداري همغږۍ کې مرسته کولی شم. طبي پرېکړې باید مسلکي ډاکټران وکړي.",
  "appointment": "د وخت او د ډاکټر یا مرکز د تایید لپاره انساني همغږي کوونکی اړین دی. دلته هېڅ وخت نه دی ثبت شوی.",
  "quote": "بیې یوازې د انساني بیاکتنې او تایید شوې ارزونې وروسته وړاندې کېږي. دلته وروستۍ بیه نه ورکول کېږي.",
  "documents": "طبي اسناد یوازې له رضایت وروسته په خوندي پورټل کې پورته کړئ. په عام پیغام‌رسان کې یې مه استوئ.",
  "visa": "کارکوونکی باید د ویزې او سفر شرطونه له رسمي سرچینو وڅېړي. ویزه نه ده صادره یا تضمین شوې.",
  "human": "له انساني همغږي کوونکي سره د اړیکې غوښتنه ثبت شوه. دا بیړنی خدمت نه دی.",
  "general": "مهرباني وکړئ خپله اداري غوښتنه څرګنده کړئ. طبي پوښتنې انساني څېړنې ته اړتیا لري.",
 },
 "prs": {
  "greeting": "سلام. برای هماهنگی اداری سفر تداوی می‌توانم رهنمایی کنم. تصمیم‌های طبی با متخصصان است.",
  "appointment": "هماهنگ‌کننده انسانی باید وقت و تأیید داکتر یا مرکز را بررسی کند. در این گفتگو وقت ثبت نشده است.",
  "quote": "هزینه‌ها تنها پس از بررسی انسانی و پیش‌فاکتور تأییدشده اعلام می‌شوند. این گفتگو قیمت قطعی نمی‌دهد.",
  "documents": "اسناد طبی را تنها با رضایت در پورتال مصون بارگذاری کنید، نه در پیام‌رسان عمومی.",
  "visa": "کارمند شرایط ویزه و سفر را با منابع رسمی بررسی می‌کند. هیچ ویزه‌ای صادر یا تضمین نشده است.",
  "human": "درخواست تماس با هماهنگ‌کننده انسانی ثبت شد. این خدمت برای حالات عاجل نیست.",
  "general": "لطفاً خواست اداری خود را توضیح دهید. مسائل طبی به بازبینی متخصص انسانی نیاز دارند.",
 },
}
# Deliberately small and conservative: ambiguity routes to general/human review.
# A deterministic keyword match is NOT a clinical intent classifier.
KEYWORDS = {
 "human": (
   "human", "operator", "person", "real agent", "representative", "speak to staff",
   "اپراتور", "انسان", "کارشناس", "هماهنگ کننده", "مسئول", "مشاور انسانی",
   "موظف", "کارمند", "انسانی", "پرسونل", "شخص حقيقي", "موظف بشري",
   "موظف", "التحدث مع شخص", "انسان سره", "کارکوونکي سره", "د انسان",
 ),
 "documents": (
   "document", "medical report", "upload", "passport photo", "scan", "test results",
   "مدرک", "مدارک", "پرونده پزشکی", "گزارش پزشکی", "بارگذاری", "آپلود",
   "اسناد", "تقرير طبي", "وثيقه", "تحميل", "رفع ملفات",
   "طبي اسناد", "راپورونه", "اپلوډ", "اسناد طبی", "راپور طبی",
 ),
 "appointment": (
   "appointment", "booking", "see a doctor", "schedule visit",
   "نوبت", "وقت ملاقات", "وقت داکتر", "رزرو پزشک",
   "موعد", "حجز موعد", "زيارة طبيب", "معاينه",
   "وخت", "د ډاکټر وخت", "ملاقات",
 ),
 "quote": (
   "cost", "price", "quotation", "how much", "estimate", "payment",
   "هزینه", "قیمت", "پیش فاکتور", "فاکتور", "مبلغ",
   "تكلفه", "السعر", "كم السعر", "تقدير السعر", "الثمن",
   "بیه", "لګښت", "قیمت تداوی", "مصارف",
 ),
 "visa": (
   "visa", "travel", "flight", "hotel",
   "ویزا", "ویزه", "سفر", "هتل", "اقامت",
   "تاشيره", "سفر", "فندق",
   "سفر", "ویزه", "هوټل",
 ),
 "greeting": (
   "hello", "hi", "good morning", "سلام", "درود",
   "مرحبا", "اهلا", "السلام عليكم", "سلامونه", "ښه راغلاست",
 ),
}
_ORDER = ("human", "documents", "appointment", "quote", "visa", "greeting")


def classify_intent(message: str) -> str:
    normalized = normalize_safety_text(message)
    for intent in _ORDER:
        if any(normalize_safety_text(term) in normalized for term in KEYWORDS[intent]):
            return intent
    return "general"


def receptionist_response(locale: str, message: str) -> dict:
    if locale not in LANGUAGES:
        raise ValueError("Unsupported language")
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 4000:
        raise ValueError("Invalid message length")
    safety = intake_response(locale, message)
    emergency = bool(safety["emergency_keyword_detected"])
    intent = "urgent_human_review" if emergency else classify_intent(message)
    human = emergency or intent == "human"
    return {
        "language": locale,
        "intent": intent,
        "message": safety["message"] if emergency else RESPONSES[locale][intent],
        "emergency_keyword_detected": emergency,
        "human_handoff_required": human,
        "human_review_required": True,
        "automatic_clinical_decision": False,
        "provider_called": False,
        "disclaimer": (
            "Deterministic administrative routing only. Not an emergency "
            "assessment, diagnosis, clinical translation or booking."
        ),
    }


class PreviewIn(BaseModel):
    language: Locale
    intent: Intent


@router.get("/catalog")
def catalog(user: User = Depends(staff)):
    return {
        "production_ready": False,
        "speech_enabled": False,
        "clinical_translation_validated": False,
        "supported_languages": [
            {"code": lang, "name": LABELS[lang], "direction": DIRECTION[lang],
             "copy_reviewed_by_native_speaker": False}
            for lang in sorted(LANGUAGES)
        ],
        "intents": list(RESPONSES["en"].keys()),
        "patient_medical_qa": False,
        "automated_booking": False,
    }


@router.post("/preview")
def preview(body: PreviewIn, user: User = Depends(staff)):
    # Controlled preview only, not a route to submit/send or log actual PHI.
    return {
        "language": body.language,
        "intent": body.intent,
        "message": RESPONSES[body.language][body.intent],
        "human_review_required": True,
        "external_message_sent": False,
    }
