# مرحله ۱۹.۱۹ — Atomic Refresh / Consent Transactions (نسخه آزمایشی)

**تاریخ: ۲۰ اکتبر ۲۰۲۶ — وضعیت: پیاده‌سازی در GitHub، در انتظار اجرای تست‌های جدید توسط کاربر.**

## شواهد تأییدشده

- ۱۹.۱۶: آزمون مسیرهای واقعی FastAPI تحت PostgreSQL/RLS در Clone — PASS.
- ۱۹.۱۷: `31 passed` تست اختصاصی توکن و `85 passed, 1 warning` تست کامل Backend.
- ۱۹.۱۸: `PASS: STAGE 19.18 ISOLATED SIGNED TENANT ROUTING AND DB HASH LOOKUP TEST COMPLETED`.

## مسئله‌ای که این مرحله حل می‌کند

آزمون موفق Lookup، جلوی یک Replay رقابتی را نمی‌گیرد. اگر دو درخواست با یک توکن در زمانی نزدیک ارسال شوند، هر کدام باید برای تغییر وضعیت Credential روی همان ردیف تحت یک تراکنش قفل‌دار قرار بگیرند؛ در غیر این صورت امکان صدور Refresh Token تکراری یا مصرف چندباره Consent وجود دارد.

## فایل‌های تحویل‌شده

1. `backend/app/staged_tenant_transactions.py`: عملیات **غیرفعال در API زنده** با `SELECT ... FOR UPDATE`، بررسی هویت ورود PostgreSQL از طریق تابع محافظت‌شده `tenant_for_login()`، و تراکنش اختصاصی هر Tenant. Refresh Token جدید به‌صورت امضاشده صادر و هش آن ذخیره می‌شود؛ Replay توکن لغوشده خانواده Refresh را باطل می‌کند. Consent Link تنها یک‌بار مصرف می‌شود و پس‌گرفتن رضایت، Portal Access و پیام‌های در صف مربوط به بیمار را مسدود می‌کند.
2. `scripts/rls-staged-transactions-probe.py`: داده ساختگی، دو نقش Login، آزمون تغییر Tenant/Purpose، چرخش Refresh، Replay و Isolation، ثبت/لغو Consent و اجرای **دو درخواست هم‌زمان به یک لینک رضایت**.
3. `scripts/rls-staged-transactions-clone-test.ps1`: اجرای آزمون PostgreSQL روی Backup توسعه ساختگی در شبکه `docker network --internal` بدون Volume و اتصال سرویس اصلی.
4. `backend/tests/test_stage_19_19_staged_transactions.py`: تست‌های سریع آفلاین Fail-Closed پیش از ورود به دیتابیس.
5. `scripts/test-stage-19-15-auth-boundaries.ps1`: گزینه `-AtomicTransactionsOnly` برای تست هدفمند.

### دستورهای PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -AtomicTransactionsOnly
& .\scripts\rls-staged-transactions-clone-test.ps1
```

بعد از موفقیت این دو، در صورت نیاز تست کامل:

```powershell
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
```

پیام پایانی مورد انتظار از Docker Clone:

```text
PASS: STAGE 19.19 ISOLATED ATOMIC REFRESH CONSENT TRANSACTION TEST COMPLETED
```

## محدودیت‌های مهم و شرط مهاجرت عملیاتی

- **این ماژول در `main.py`، `session_api.py` یا `consent_links.py` فراخوانی نمی‌شود.** API زنده فعلاً از Router جدید بهره نمی‌برد.
- **Login/Health/Webhook/Staff JWT** همچنان به اتصال فعلی و انتخاب Tenant قبل از Login وابسته هستند.
- سرویس آزمایشی صرفاً Transactional Credential را تغییر می‌دهد، Access JWT جدید صادر نمی‌کند و کنترل نسخه Privacy Notice/هویت بیمار باید در لایه HTTP جداگانه انجام شود.
- توکن‌های قدیمی Refresh/Portal/Consent فاقد Routing Hint امضاشده‌اند و قبل از مهاجرت باید برایشان دوره انتقال سازگار طراحی شود.
- مدارک بالینی یا مالی واقعی نباید در آزمون‌ها استفاده شوند. هیچ تنظیمات RLS روی دیتابیس عملیاتی، Credentialهای `.env`، Secret و Compose نباید در این مرحله تغییر کنند.
- **خطر عملکردی:** replay حتی اگر به‌دلیل retry درخواست مجدد رخ دهد، در این طراحی کل خانواده Refresh را revoke می‌کند. قبل از Production باید سیاست UX/Retry و Idempotency در شرایط قطع پاسخ ارزیابی شود.
- مهم‌ترین مرحله بعد ساخت و آزمایش Runtime واقعی Tenant Resolver و اتصال Dependencyهای FastAPI با نقش‌های غیرمدیریتی است، سپس Migration همراه Backup/Rollback.
