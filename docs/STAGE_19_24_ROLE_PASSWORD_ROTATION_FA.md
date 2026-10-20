# مرحله ۱۹.۲۴ — چرخش واقعی رمز PostgreSQL در Clone موقت

**تاریخ: ۲۰ اکتبر ۲۰۲۶. وضعیت: فایل‌ها در `main` ثبت شده‌اند؛ تست‌های ۱۹.۲۴ هنوز توسط کاربر اجرا نشده‌اند.**

## شواهد تکمیل‌شده

- مرحله ۱۹.۲۲: تست Registry/Lease و PostgreSQL RLS هر دو PASS.
- مرحله ۱۹.۲۳: `PASS: STAGE 19.23 ISOLATED MULTIWORKER TENANT EPOCH REVOCATION TEST COMPLETED` (طبق خروجی کاربر).

## مسئله

چرخش `generation` در مرحله ۱۹.۲۳ دسترسی جدید را کنترل می‌کند، اما رمز قبلی ورود PostgreSQL را عوض نمی‌کند و اتصال‌های فعال را نمی‌بندد. بنابراین برای چرخش واقعی باید مسیر مدیریتی **کاملاً جدا از API** وجود داشته باشد تا بر اساس Epoch غیرفعال‌شده رمز را تغییر دهد، نشست‌های قدیمی را پایان دهد و تنها پس از تأیید، Tenant مجدداً فعال شود.

## فایل‌های جدید

- `backend/app/staged_rotation_contract.py`: بررسی غیرمدیریتی اینکه Tenant، Role، آدرس DB و سایر شناسه‌ها در چرخش بدون تغییر مانده‌اند، رمز جایگزین متفاوت است و `EpochState(generation=2, enabled=False)` از Control Reader معتبر دریافت شده است؛ خروجی فاقد هر دو رمز است.
- `backend/tests/test_stage_19_24_rotation.py`: تست‌های Fail-Closed قرارداد قبل از اعمال تغییر.
- `scripts/rls-role-password-rotation-clone-setup.sql`: **فقط روی دیتابیس Clone** نقش `mt_rotation_operator` با مجوز محدود اجرای تابع `medtour_control.rotate_synthetic_a` ایجاد می‌کند. تابع `SECURITY DEFINER` با کنترل اجباری `session_user`، Tenant A ثابت، Epoch دقیق ۲ در وضعیت غیرفعال، رمز با طول/فرمت محدود و جدول جلوگیری از اجرای تکراری، فقط رمز `mt_clone_a` را تغییر می‌دهد و با `pg_terminate_backend(...,5000)` بسته‌شدن نشست‌های قدیمی را انتظار می‌کشد. Operator اجازه خواندن بیمار، ایجاد Role یا تغییر Epoch ندارد.
- `scripts/rls-role-password-rotation-probe.py`: تست دو Registry مستقل، جداسازی Tenant B، قطع Lease جدید با Epoch ۲، اجرای Rotation مجاز، قطع نشست قدیمی، رد رمز قبلی در اتصال تازه، پذیرش رمز جدید، رد Replay، فعال‌سازی Epoch ۳ و Provision مجدد هر دو Registry تحت RLS.
- `scripts/rls-role-password-rotation-clone-test.ps1`: تمام نقش‌ها و Passwordهای تصادفی را فقط برای دیتابیس PostgreSQL موقت و `docker network --internal` ایجاد می‌کند؛ با پایان آزمون، کانتینرها و شبکه پاک می‌شوند. هیچ Volume و سرویس Compose عملیاتی دست‌کاری نمی‌شود.

## مراحل cutover در Clone

```text
1. Worker A/B: Tenant A & B under verified RLS roles (epoch 1)
2. Tenant A: block new leases (epoch 2, enabled=false) — B remains enabled
3. Trusted restricted operator: change mt_clone_a password + terminate old sessions
4. Confirm old credential denied on FRESH TCP connection; new credential works
5. Confirm no repeated rotation in same epoch; B unaffected
6. Control writer: epoch 3, enabled=true
7. Both workers: stale config blocked, then explicitly provision new credential
8. Verify A and B patient isolation under RLS and no privileged fallback
```

## اجرای PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -CredentialRotationOnly
& .\scripts\rls-role-password-rotation-clone-test.ps1
```

بعد از موفقیت، می‌توان تست رگرسیون را با `-FullSuite` اجرا کرد.

پیام نهایی مورد انتظار:

```text
PASS: STAGE 19.24 ISOLATED TENANT POSTGRESQL CREDENTIAL ROTATION TEST COMPLETED
```

## محدودیت‌های امنیتی مهم

1. **Clone-only:** تابع دارای مجوز بالاتر و Role مخصوص چرخش فقط در دیتابیس دورریختنی آزمایش ساخته می‌شوند. فایل SQL با نام دیتابیس و Tenant ثابت Guard شده است. **این SQL را مستقیماً روی هیچ DB عملیاتی اجرا نکنید.**
2. **رمزهای حساس:** فایل PowerShell رمزهای تصادفی ساختگی تولید می‌کند. در Production باید Secret Manager، گردش نسخه Secret، ثبت Audit بدون مقدار Secret، تایید دو‌نفره برای عملیات حساس و ذخیره امن Credential به‌طور مستقل ساخته شود.
3. **Sessionهای فعال:** `pg_terminate_backend` می‌تواند درخواست درحال اجرا را قطع کند؛ آزمون عمداً چنین اثری را بررسی می‌کند. برای Production نیاز به Drain، زمان‌بندی، اعلام آماده‌سازی، Retry امن و rollback با تأیید مستقل وجود دارد.
4. **Idempotence و rollback:** تابع تست برای جلوگیری از دو بار تغییر رمز در یک Epoch، History نگه می‌دارد. این به معنی وجود Runbook تولیدی با Rollback امن نیست.
5. **چند Process واقعی:** دو Registry در یک Process تست می‌شوند، نه چند Pod/Process عملیاتی.
6. **API عملیاتی:** کد `main.py`، `database.py`، `get_db`، Docker Compose، جدول‌های واقعی و Alembic تغییر نکرده‌اند. Login/Refresh/Portal/Consent/WhatsApp هنوز در Runtime اصلی مهاجرت نکرده‌اند.
7. **حفاظت کلیدها:** رمز PostgreSQL متفاوت از کلید JWT و HMAC مسیریابی توکن است؛ چرخش DB Secret، توکن‌های قدیمی و اطلاعات پزشکی را به‌خودی‌خود امن یا باطل نمی‌کند.

**در صورت موفقیت این مرحله، فقط چرخش و Recovery روی Clone اثبات می‌شود؛ Production همچنان آماده مهاجرت نهایی نیست.**
