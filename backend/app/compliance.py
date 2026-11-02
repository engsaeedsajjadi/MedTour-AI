"""Real-patient readiness gate.

Legal and regulatory approval cannot be produced by code. What the code can do is refuse to run
with real patients until every technical control is active AND an operator has recorded the
references of the legal decisions (privacy notice, data-protection review, provider contracts).

Set REAL_PATIENT_DATA_MODE=true only after all checks below pass; the API will not start otherwise.
"""
from __future__ import annotations
import os
from fastapi import APIRouter, Depends
from .database import engine
from .models import User
from .security import roles, staff_mfa_required

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _release_ok() -> bool:
    from .release_approval import evaluate
    return evaluate()["authorized"]


def checks() -> list[dict]:
    from .secure_media import s3_ready
    from .otp_delivery import configured as otp_configured
    from .tenant_rls import runtime_status
    rls = False
    if engine.dialect.name == "postgresql":
        try:
            with engine.connect() as conn:
                rls = runtime_status(conn)["rls_effective"]
        except Exception:
            rls = False
    notice_url = _env("PUBLIC_PRIVACY_NOTICE_URL")
    items = [
        ("tenant_isolation", "جداسازی سازمان‌ها با RLS و نقش غیرممتاز پایگاه داده", rls, "technical"),
        ("staff_mfa", "ورود دومرحله‌ای اجباری کارکنان", staff_mfa_required() and bool(_env("MFA_ENCRYPTION_KEY")), "technical"),
        ("patient_otp", "ارسال کد ورود بیمار از کانال تأییدشده (ایمیل/پیامک)", otp_configured(), "technical"),
        ("document_storage", "مخزن امن مدارک با اسکن بدافزار", s3_ready(), "technical"),
        ("retention_policy", "دوره نگهداری مدارک تعریف شده", bool(_env("MEDICAL_DOCUMENT_RETENTION_DAYS")), "technical"),
        ("privacy_notice", "اطلاعیه حریم خصوصی حقوقی و منتشرشده (HTTPS)",
         notice_url.startswith("https://") and _env("PRIVACY_NOTICE_VERSION") not in ("", "v0-development"), "legal"),
        ("privacy_notice_approval", "مرجع تأیید حقوقی اطلاعیه حریم خصوصی", bool(_env("PRIVACY_NOTICE_APPROVAL_REFERENCE")), "legal"),
        ("data_protection_review", "مرجع بررسی حقوقی حفاظت داده سلامت در کشورهای هدف", bool(_env("DATA_PROTECTION_REVIEW_REFERENCE")), "legal"),
        ("provider_contracts", "مرجع قرارداد و تأیید ارائه‌دهندگان (هوش مصنوعی، پیام‌رسان، پرداخت، ذخیره‌سازی)", bool(_env("PROVIDER_CONTRACTS_REFERENCE")), "legal"),
        ("medical_license", "مرجع مجوزهای فعالیت گردشگری سلامت", bool(_env("MEDICAL_TOURISM_LICENSE_REFERENCE")), "legal"),
        ("rate_limit_store", "ذخیره‌ساز مشترک محدودیت ورود (Redis)", bool(_env("REDIS_URL")), "technical"),
        ("release_approval", "تأیید انتشار: تست نفوذ، بازبینی ایمنی بالینی و حریم خصوصی، تمرین بازیابی پشتیبان", _release_ok(), "review"),
    ]
    return [{"key": k, "label": label, "passed": bool(ok), "kind": kind} for k, label, ok, kind in items]


def readiness() -> dict:
    result = checks()
    ready = all(item["passed"] for item in result)
    return {"real_patient_data_mode": _env("REAL_PATIENT_DATA_MODE").lower() == "true" or _env("APP_ENV") == "production",
            "ready_for_real_patients": ready, "checks": result}


def enforce_real_patient_mode() -> None:
    # Production always carries real patient data, so it is held to the full checklist.
    if _env("REAL_PATIENT_DATA_MODE").lower() != "true" and _env("APP_ENV") != "production":
        return
    failed = [item["key"] for item in checks() if not item["passed"]]
    if failed:
        raise RuntimeError("Real-patient operation refused; missing controls: " + ", ".join(failed))


@router.get("/readiness")
def get_readiness(user: User = Depends(roles("admin"))):
    # Reports configuration state only; never discloses secrets, DSNs or reference contents.
    return readiness()
