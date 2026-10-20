# مرحله ۱۹.۲۰ — اتصال درخواست HTTP به نقش مستقل PostgreSQL (Clone Only)

**تاریخ: ۲۰ اکتبر ۲۰۲۶. وضعیت: تست Fail-Closed Unit و آزمون FastAPI با PostgreSQL RLS در Clone هر دو با پیام PASS توسط کاربر تأیید شده‌اند. اتصال Production همچنان تغییر نکرده است.**

## وضعیت قبلی (شواهد کاربر)

- ۱۹.۱۵: `54 passed, 1 warning` تست Backend.
- ۱۹.۱۶: `PASS: STAGE 19.16 ISOLATED FASTAPI POSTGRESQL RLS ENDPOINT TEST COMPLETED`.
- ۱۹.۱۷: `31 passed` توکن و `85 passed, 1 warning` مجموعه کامل Backend.
- ۱۹.۱۸: `PASS: STAGE 19.18 ISOLATED SIGNED TENANT ROUTING AND DB HASH LOOKUP TEST COMPLETED`.
- **۱۹.۱۹:** `PASS: STAGE 19.19 ATOMIC TRANSACTION UNIT TESTS COMPLETED` و `PASS: STAGE 19.19 ISOLATED ATOMIC REFRESH CONSENT TRANSACTION TEST COMPLETED`. این اثبات RLS و اتمیک بودن عملیات روی Clone است، نه اتصال Production.

## محدوده واقعی این مرحله

`backend/app/staged_http_tenant_router.py` کلاس `StagedHttpTenantRouter` را معرفی می‌کند که در **هیچ مسیر اجرایی app.main و get_db اصلی فعال نیست**. TestClient با `app.dependency_overrides[get_db]` به‌صورت موقت، برای هر درخواست به جای انتخاب ثابت DB در ابتدای آزمون، Tenant را از Credential خود درخواست تعیین می‌کند:

- **Staff:** مسیرهای منتخب `/api/v1/auth/me`، `/api/v1/auth/logout`، `/api/v1/patients`، `/api/v1/cases` و `/api/v1/dashboard` پس از بررسی امضای JWT HS256 و فیلد `tid` به Role مربوطه متصل می‌شوند؛ سپس `current_user` عضویت فعال/Revocation را در همان DB مجدداً بررسی می‌کند.
- **Patient Portal:** برای `/api/v1/portal/me`، `/journey` و `/chat` ابتدا امضای MAC روی `X-Patient-Access`، وجود هش توکن و لغو/انقضای آن با Role مجزا بررسی می‌شود.
- **Consent:** مسیرهای موجود `/api/v1/consent-links/preview` و `/respond` بعد از MAC و جست‌وجوی Hash با اتصال Tenant اجرا می‌شوند. عملیات `/respond` در کد جاری FastAPI همچنان `SELECT FOR UPDATE` و ثبت یک‌باره را انجام می‌دهد؛ ماژول جدید تراکنش مرحله ۱۹.۱۹ هنوز به Endpointهای عملیاتی وصل نشده است.
- **تطبیق نقش DB:** حتی پس از انتخاب Pool، `session_user` باید در تابع خصوصی `medtour_principal_private.tenant_for_login()` به Tenant مورد انتظار نگاشت شود.
- **عدم fallback:** هیچ اتصال مدیریتی، نقش Superuser یا Tenant پیش‌فرض برای توکن نامعتبر یا خرابی DB استفاده نمی‌شود.

### مسیرهای عمداً غیرقابل استفاده در این PoC

- **Login:** فعلاً `Tenant.slug` را از جدول سراسری `tenants` پیدا می‌کند؛ نقش Tenant به آن دسترسی ندارد. نیاز به Registry کاملاً محدود و اعتبارسنجی پس از انتخاب Tenant دارد.
- **Refresh:** Endpoint فعلی Refresh Token قدیمی و فاقد MAC صادر می‌کند؛ مهاجرت ایمن صدور/مصرف، نگه‌داری کلیدهای قدیمی و Replay/Idempotency آماده نیست. استفاده از این Endpoint در PoC ممنوع است تا Refresh جدید غیرقابل‌استفاده صادر نشود.
- **WhatsApp Webhook:** امضای Meta، `phone_number_id` و Tenant Registry باید پیش از Session انتخاب شوند؛ در Handler فعلی هنوز جست‌وجوی `Tenant.slug` انجام می‌شود.
- **Health/Ready:** همچنان از شمارش جدول سراسری `tenants` استفاده می‌کند و با Role محدود مجاز نیست.
- **سایر Routeها:** برای کاهش سطح حمله، allowlist این PoC محدود است. بدون پوشش صریح مسیر، درخواست 503 می‌گیرد.

### ریسک‌های برجسته

1. لینک `GET consent-links/preview?token=...` همچنان توکن حساس را در URL قرار می‌دهد. قبل از PHI واقعی به Header/POST منتقل شود.
2. تمام Connectionها باید با سقف Pool، Credential منفرد و Secret Manager مدیریت شوند. در این مرحله فقط Factoryهای پیش‌تأمین‌شده آزمایشی مصرف می‌شوند.
3. کلیدهای HMAC مستقل از JWT و Credentialهای DB باید مدیریت/چرخش و ابطال شوند.
4. Login، Refresh، Logout، Webhook، Health، پرونده پزشکی، Documents و تمامی Endpointهای دیگر به Migration واقعی و تست‌های Integration نیاز دارند. `Logout` فقط در Allowlist است و باید در آزمون بعدی به‌صورت End-to-End پوشش داده شود.
5. Database Schema واقعی هنوز RLS ندارد؛ تست فقط روی Backup ساختگی Restoreشده در کانتینر داخلی اجرا می‌شود.

## فایل‌های مرحله ۱۹.۲۰

- `backend/app/staged_http_tenant_router.py`: Tenant Router غیرفعال در Production.
- `backend/tests/test_stage_19_20_http_router.py`: تست‌های Fail-Closed بدون نیاز به PostgreSQL.
- `scripts/rls-request-bound-fastapi-probe.py`: یک TestClient مشترک برای دو Tenant؛ تأیید JWT، مشاهده پرونده، IDOR، لینک بیمار/رضایت، جلوگیری از جعل، و رد مسیرهای پشتیبانی‌نشده.
- `scripts/rls-request-bound-fastapi-clone-test.ps1`: اجرای تست روی `docker network --internal` در PostgreSQL Clone، بدون Volume و API فعال.

## اجرای Windows PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -HttpRouterOnly
& .\scripts\rls-request-bound-fastapi-clone-test.ps1
```

پس از موفقیت، در صورت نیاز:

```powershell
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
```

پیام نهایی مورد انتظار:

```text
PASS: STAGE 19.20 ISOLATED REQUEST-BOUND FASTAPI TENANT ROUTING TEST COMPLETED
```

## شرط خروج معماری Production

یک آزمون TestClient با Override کافی نیست. قبل از پذیرش باید Tenant Registry با حداقل دسترسی، Login/Refresh/Portal/Consent/Webhook کامل، مدیریت Pool و Secret Lifecycle، RLS و FKهای مرکب با Migration/Backout امن، مانیتورینگ و UAT مستند شوند. تا آن زمان **اتصال Superuser فعلی یا RLS دیتابیس اصلی را تغییر ندهید**.
