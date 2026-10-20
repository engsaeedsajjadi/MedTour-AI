# مرحله ۱۹.۱۸ — اثبات اتصال Token Hint امضاشده به PostgreSQL با RLS

**وضعیت:** آزمون روی PostgreSQL ایزوله با پیام `PASS: STAGE 19.18 ISOLATED SIGNED TENANT ROUTING AND DB HASH LOOKUP TEST COMPLETED` توسط کاربر تأیید شد. اتصال عملیاتی API همچنان تغییر نکرده است.

## آخرین وضعیت تأییدشده

- مرحله ۱۹.۱۶: `PASS: STAGE 19.16 ISOLATED FASTAPI POSTGRESQL RLS ENDPOINT TEST COMPLETED` توسط کاربر تأیید شده است.
- مرحله ۱۹.۱۷: `31 passed` برای تست‌های توکن و `85 passed, 1 warning` برای مجموعه کامل تست‌های Backend، توسط کاربر تأیید شده‌اند.

## کد افزوده‌شده در این مرحله

- `backend/app/tenant_credential_lookup.py`: Resolver مستقل و **غیرفعال در API زنده** با `TenantRouteKeyring` و SessionFactoryهای معرفی‌شده از سمت سرور.
- `scripts/rls-signed-token-router-probe.py`: ساخت داده‌های ساختگی زیر نقش‌های واقعی Tenant، تست صحت MAC، تغییر Tenant/Purpose، بررسی Hash توکن، انقضا، Revocation، Consumed Link، و اشتباه در نگاشت Tenant به Pool.
- `scripts/rls-signed-token-router-clone-test.ps1`: بازیابی آخرین Backup توسعه ساختگی در PostgreSQL موقت با `docker network --internal`، ساخت دو Login مستقل، فعال‌سازی ۳۷ Policy، و اجرای Probe در کانتینر مستقل Python.

## ترتیب کنترل امنیتی

```text
Untrusted token
    → validate version, expected purpose, expiry, HMAC
    → extract authenticated tenant routing hint
    → find tenant in trusted server-side session directory
    → connect using independently authenticated tenant PostgreSQL LOGIN
    → check DB login's private tenant mapping (session_user)
    → SELECT stored SHA-256(full token) under RLS
    → verify row expiry, revocation / one-time usage
    → return opaque row ID only
```

بدون امضای معتبر، **هیچ Session جدیدی ساخته نمی‌شود**. خطای ارتباط DB یا نقش اشتباه نباید به Connection مدیریتی یا Tenant پیش‌فرض سقوط کند.

**این مرحله در محیط ایزوله فقط Lookup را بررسی می‌کند؛ Refresh Rotation واقعی، مصرف اتمیک Consent Token، و فعال‌سازی Router در Handlerهای FastAPI هنوز پیاده‌سازی نشده‌اند.**

## اجرای Windows PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\rls-signed-token-router-clone-test.ps1
```

پیام نهایی در صورت موفقیت:

```text
PASS: STAGE 19.18 ISOLATED SIGNED TENANT ROUTING AND DB HASH LOOKUP TEST COMPLETED
```

## محدودیت‌ها و کارهای باقی‌مانده

1. **مهاجرت توکن‌های قدیمی:** توکن‌های Refresh/Portal/Consent قبلی فاقد Hint امضاشده‌اند؛ برای انتقال بی‌وقفه یا پایان‌دادن امن به عمرشان طرح جداگانه لازم است.
2. **Routing واقعی HTTP:** `get_db` سراسری، Login/Refresh/Portal/Consent و Webhook Meta هنوز بدون استفاده از Resolver جدید اجرا می‌شوند. استقرار مستقیم این تغییرات مجاز نیست.
3. **کنترل ظرفیت و اسرار:** `Tenant → DB role → credential` باید از Secret Manager، با سقف اتصال و قابلیت چرخش/ابطال، تأمین شود؛ کلید HMAC نباید از ورودی یا کلید JWT مشترک گرفته شود.
4. **Atomicity:** Lookup توکن معتبر به‌تنهایی مانع Replay رقابتی نیست؛ مصرف/چرخش باید در یک تراکنش با `FOR UPDATE` و کنترل حالت انجام شود.
5. **پایه داده/Schema:** `ENABLE/FORCE RLS` و ۴۸ Foreign Key مرکب هنوز فقط روی Clone بررسی شده‌اند. Migration عملیاتی + Backup/Restore/Rollback + تأیید مستقل باقی است.
6. **سلامت، Bootstrap، Tenant Slug و Webhook:** این مسیرها به Registry با حداقل مجوز و ارزیابی جداگانه نیاز دارند.
7. **حریم خصوصی:** توکن Consent در Query String همچنان خطر نشت در URL/History/Referrer دارد و قبل از ورود داده واقعی بیمار باید بازطراحی شود.

**هیچ کد API یا تنظیمات Docker Compose عملیاتی و هیچ داده/Volume فعال نباید در این مرحله تغییر کند.**
