# مرحله ۱۹.۲۲ — Tenant Pool Registry: ظرفیت، هویت دیتابیس و ابطال ایمن

**وضعیت:** کد و تست‌ها در شاخه `main` ثبت شده‌اند؛ هنوز نتایج اجرای مرحله ۱۹.۲۲ در سیستم کاربر دریافت نشده است.

## مرحله‌های تأییدشده

- ۱۹.۱۹: Unit و آزمون اتمیک Refresh/Consent با PostgreSQL/RLS هر دو PASS.
- ۱۹.۲۰: Unit و آزمون Route-to-Tenant برای درخواست‌های واقعی FastAPI با PostgreSQL/RLS هر دو PASS.
- ۱۹.۲۱: `8 passed, 1 warning` در تست اختصاصی Pre-auth و `PASS: STAGE 19.21 ISOLATED PREAUTH LOGIN REFRESH WEBHOOK ROUTING TEST COMPLETED` در PostgreSQL Clone. هشدار TestClient مربوط به Deprecation است، نه شکست امنیتی.

## پیاده‌سازی ۱۹.۲۲

`backend/app/staged_tenant_pool_registry.py` یک Registry **فقط آزمایشی، غیرفعال در FastAPI اصلی** ایجاد می‌کند که صرفاً از `TenantPrincipalConfig` معتبر و از پیش‌تأمین‌شده استفاده می‌کند.

**اقدام‌های امنیتی:**

1. هویت `session_user` و `current_user` در PostgreSQL و نگاشت خصوصی `medtour_principal_private.tenant_for_login()` قبل از معرفی Pool به بقیه بخش‌ها بررسی می‌شود.
2. نقش نمی‌تواند Superuser، `BYPASSRLS`، سازنده Role/DB یا دارای دسترسی مستقیم به `public.tenants` باشد.
3. مسیر Lookup از طریق `tenant_id`، `slug` یا `WhatsApp phone_number_id` تنها برای مقادیر ثبت‌شده در Registry فعال است. این مقادیر در Endpointها یا Headerها امکان ایجاد نقش جدید ندارند.
4. نگاشت تکراری Tenant/Slug/شماره حساب، استفاده هم‌زمان از Login یکسان برای دو Tenant و Registry بیش از ظرفیت رد می‌شود.
5. سقف نمونه آزمایشی: حداکثر ۱۶ Tenant در هر Process، حداکثر ۴ Connection ثابت در هر Pool، بودجه هم‌زمان Pool برابر حداکثر ۳۲ Connection؛ `max_overflow=0`، `pool_timeout=5`، `pool_pre_ping=True` و `connect_timeout=5`.
6. `revoke()` امکان دریافت Lease جدید را فوراً قطع می‌کند، ولی Sessionهای شروع‌شده را تا پایان Lease با همان نقش نگه می‌دارد؛ بعد از آخرین Lease، Pool مربوطه Dispose می‌شود. استفاده مجدد از Role تا پایان تخلیه ممنوع است.
7. `close()` همه مسیرهای جدید را می‌بندد و Poolهای بلااستفاده را Dispose می‌کند. شمارنده‌های `snapshot_counts()` تعداد Leaseهای باقی‌مانده و Poolهای در حال تخلیه را بدون افشای Credential گزارش می‌دهند.
8. Secret در `repr(TenantPrincipalConfig)` پنهان است و در خود Slot پس از Enroll دیگر نگه‌داری نمی‌شود؛ با این حال SQLAlchemy Engine ممکن است اطلاعات Credential را برای اتصال‌های بعدی در حافظه نگاه دارد و نباید فرض کرد Secret از تمام حافظه پاک شده است.

## فایل‌های تست

- `backend/tests/test_stage_19_22_tenant_registry.py`: آزمون‌های آفلاین مربوط به ثبت، رد Duplicate، محدودیت ظرفیت، نگاشت اشتباه DB، Role ممتاز، Lease هم‌زمان، Revocation و Shutdown.
- `scripts/rls-tenant-pool-registry-probe.py`: آزمون واقعی PostgreSQL 17 با نقش `mt_clone_a` و `mt_clone_b` و Policyهای RLS روی کپی ایزوله: مشاهده رکوردهای خودی، جلوگیری از نشت Tenant دیگر، کنترل اتصال‌های هم‌زمان، رد Pool اشتباه و لغو در زمان Lease.
- `scripts/rls-tenant-pool-registry-clone-test.ps1`: اجرای Python و PostgreSQL داخل `docker network --internal` بدون دست‌زدن به Compose و Volume فعال.

## اجرا در PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -TenantRegistryOnly
& .\scripts\rls-tenant-pool-registry-clone-test.ps1
```

برای بررسی رگرسیون کامل:

```powershell
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
```

پیام مورد انتظار از PostgreSQL Clone:

```text
PASS: STAGE 19.22 ISOLATED TENANT POOL REGISTRY LIFECYCLE TEST COMPLETED
```

## محدودیت‌های عملیاتی مهم

**این Registry هنوز نباید در Production فعال شود.** استقرار واقعی Multi-worker نیازمند کنترل مرکزی و آنیِ ابطال بین همه Workerها، پایش Endpointهای Health، Secret Manager، Rotation نقش/رمز، سقف کلی Connection در تمام Podها/Workerها، Provisioning و Deprovisioning تأییدشده و هماهنگی هنگام تغییر نگاشت نقش PostgreSQL است.

این کد هنوز در `main.py`، `database.py`، `get_db`، Routeهای اصلی، Alembic، WhatsApp Processor و پردازش PHI وصل نیست. هیچ Migration روی دیتابیس اصلی اجرا نشده و اعمال مستقیم RLS/Composite FK همچنان ممنوع است.
