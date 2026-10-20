# MedTour AI — مرحله ۱۹.۲۱: Login / Refresh / Meta pre-auth با نقش‌های Tenant

**تاریخ:** ۲۰ اکتبر ۲۰۲۶  
**وضعیت:** تست‌ها توسط کاربر تأیید شدند: `8 passed, 1 warning` در Unit و `PASS: STAGE 19.21 ISOLATED PREAUTH LOGIN REFRESH WEBHOOK ROUTING TEST COMPLETED` در PostgreSQL Clone. هنوز هیچ مهاجرت Production انجام نشده است.

## آخرین نتیجه تأییدشده

- ۱۹.۱۹: تست اتمیک Refresh / Consent در PostgreSQL Clone — موفق.
- ۱۹.۲۰: Unit Test Fail-closed و FastAPI Request-Bound Routing در PostgreSQL Clone — هر دو با پیام `PASS` توسط کاربر تأیید شده‌اند.

## محدوده و ماهیت تغییرات جدید

**هیچ‌کدام از فایل‌های `backend/app/main.py`، `backend/app/database.py`، `backend/app/session_api.py`، `backend/app/whatsapp.py`، `backend/app/patient_portal.py` یا `backend/app/consent_links.py` در این مرحله تغییر نکرده‌اند.**

- `backend/app/staged_preauth_service.py`: سرویس غیرمتصل به API عملیاتی برای Login با Tenant Slug موجود در **Registry مورداعتماد سروری**، احراز رمز عبور از `users` تحت نقش واقعی Tenant، صدور JWT و Refresh Token امضاشده؛ Refresh با تراکنش قفل‌دار و Replay مرحله ۱۹.۱۹؛ و بررسی امضای خام Meta و `phone_number_id` قبل از تعیین اتصال DB.
- `backend/app/staged_preauth_http.py`: روتر مستقل FastAPI که **توسط `main.py` Mount نشده است**. در TestClient، مسیرهای همانند `/api/v1/auth/login`، `/api/v1/auth/refresh` و `/api/v1/webhooks/whatsapp` را با سرویس فوق اجرا می‌کند. Rate Limit Login/Refresh فعال است و پیام خام WhatsApp ذخیره/ارسال نمی‌شود.
- `backend/tests/test_stage_19_21_preauth.py`: Unit Tests بدون اتصال DB برای وضعیت Fail-closed.
- `scripts/rls-preauth-login-refresh-whatsapp-probe.py`: تست HTTP واقعی در TestClient مستقل و دو Connection Pool احرازشده با PostgreSQL RLS، بررسی Hash توکن Refresh، Cross-Tenant Login، Replay/Family Revocation، و چند حالت مثبت/منفی امضای Meta.
- `scripts/rls-preauth-login-refresh-whatsapp-clone-test.ps1`: اجرای همه تست‌های Integration روی PostgreSQL 17 موقت، بازیابی Backup توسعه **فقط حاوی داده ساختگی** و `docker network create --internal`. سرویس اصلی، Volumeها، Docker Compose و فایل محیطی کاربر تغییری نمی‌کنند.
- `scripts/test-stage-19-15-auth-boundaries.ps1`: پرچم `-PreauthOnly` برای تست هدفمند؛ `-FullSuite` برای مجموعه Backend.

## معماری مرحله‌ای و شرط‌های امنیتی

```text
LOGIN:
  client tenant_slug (candidate, NOT proof)
   → trusted server-side slug-to-tenant registry (only provisioned tenants)
   → pre-provisioned non-superuser PostgreSQL LOGIN role
   → session_user verified against private role_tenant_mapping
   → users lookup scoped by tenant_id + email + active
   → password hash validation
   → atomic persisted refresh hash under same RLS role
   → signed short-lived access JWT + 7-day MAC-bound refresh

REFRESH:
  MAC-verified signed refresh
   → authenticated role associated with tenant hint
   → SELECT FOR UPDATE + tenant/user/expiry/revocation checks
   → family replay rules + atomic rotate
   → new JWT only after commit

META WEBHOOK (ROUTING ONLY):
  raw request body + X-Hub-Signature-256
   → verify Meta HMAC using approved server secret
   → parse bounded, approved phone_number_id from signed payload
   → trusted provider-account-to-tenant registry
   → assert authenticated role and protected tenant mapping
   → respond VALIDATED ONLY; NO patient message stored or sent
```

## دستور اجرا در PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -PreauthOnly
& .\scripts\rls-preauth-login-refresh-whatsapp-clone-test.ps1
```

در صورت نیاز کل تست‌های Backend:

```powershell
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
```

پیام موفقیت نهایی مرحله ۱۹.۲۱:

```text
PASS: STAGE 19.21 ISOLATED PREAUTH LOGIN REFRESH WEBHOOK ROUTING TEST COMPLETED
```

## آنچه هنوز آماده Production نیست

1. **Registry و Provisioning واقعی:** نگاشت `tenant_slug` و حساب Meta به Role/Secret اکنون صرفاً از پیش داخل تست تنظیم می‌شود. ایجاد/ابطال/تغییر نام Tenant، Key/Secret Rotation، Cache Invalidation و مدیریت ظرفیت Poolها باید طراحی و آزمایش شوند. از اتصال مدیریتی Superuser در Runtime HTTP استفاده نشود.
2. **توکن‌های Legacy:** Refreshهای قبلی و لینک‌های Portal/Consent فاقد Tenant Routing MAC هستند. پیش از تعویض Backend باید برنامه انتقال امن و بدون قطع خدمت تدوین شود؛ هیچ fallback آزاد به نقش Superuser مجاز نیست.
3. **WhatsApp inbound واقعی:** Handler کنونی همچنان پس از امضای Meta، `Tenant.slug` را از جدول سراسری می‌خواند. آداپتور آزمایشی **فقط** Routing را تأیید می‌کند و پیام‌ها را پردازش/ذخیره نمی‌کند. Consent، Idempotency، مانیتورینگ، Replay و Human Review باید در Handler واقعی پس از انتخاب Pool مجدداً آزمون شوند. مجوز واقعی WhatsApp Business و تأیید پردازش داده نیز مستقل از این آزمون است.
4. **تمام Routeها و Health:** اکثر Routeهای FastAPI از `get_db` عمومی استفاده می‌کنند. این گام `get_db` واقعی و Credential Runtime را تغییر نداده است.
5. **Migration:** RLS و ۴۸ FK مرکب هنوز در محیط اصلی فعال نیستند و روی Clone جداگانه اثبات شده‌اند. قبل از تغییر Production برنامه Backup، Rollback، مهاجرت Alembic، پایش و تأیید امنیت مستقل لازم است.
6. **حریم خصوصی/پزشکی:** قبل از استفاده با PHI واقعی، مسیر ارسال اسناد، نسخه Privacy Notice، ذخیره‌سازی حساس و ثبت رضایت به بررسی حقوقی، امنیتی و عملیاتی نیاز دارد.

**موفقیت آزمایش ۱۹.۲۱ (در صورت وقوع) به معنی فعال شدن این مسیرها در API اصلی نخواهد بود.**
