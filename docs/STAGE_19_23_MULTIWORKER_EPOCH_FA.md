# مرحله ۱۹.۲۳ — ابطال Tenant بین چند Worker با Central Epoch

**تاریخ: ۲۰ اکتبر ۲۰۲۶ — وضعیت: کد و آزمون‌ها در GitHub ثبت شده‌اند؛ PASS اجرای محلی/Clone این مرحله هنوز دریافت نشده است.**

## نتایج قطعی مراحل قبلی

- ۱۹.۲۱: ۸ تست Unit و آزمون Login/Refresh/Meta در PostgreSQL Clone موفق
- ۱۹.۲۲: تست Unit Registry/Lease و آزمون PostgreSQL Clone با پیام `PASS: STAGE 19.22 ISOLATED TENANT POOL REGISTRY LIFECYCLE TEST COMPLETED` موفق

## مسئله

`StagedTenantPoolRegistry` مربوط به ۱۹.۲۲ فقط داخل یک Process کار می‌کند. اگر Worker A یک Tenant را ابطال کند، Worker B ممکن است همچنان در Registry محلی خود برای Tenant ابطال‌شده Pool داشته باشد. اتکا به پیام Publish/Subscribe بدون بررسی منبع معتبر در هر Lease امنیت قابل اتکایی ایجاد نمی‌کند.

## مرحله جدید

- `backend/app/staged_tenant_epoch_control.py`: هر Worker یک `StagedCoordinatedTenantRegistry` مستقل دارد. قبل از **هر Lease جدید**، `PostgreSQLEpochReader` نسل دسترسی `generation` و وضعیت `enabled` را مستقیماً از جدول کنترل مرکزی و با Role فقط‌خواندنی می‌خواند. نتیجه در این مرحله Cache نمی‌شود. درخواست با نسل تغییر‌یافته/غیرفعال رد و Pool قدیمی Worker بازنشسته می‌شود. قطع/خرابی Control Plane نیز Fail-Closed است.
- `scripts/rls-central-tenant-epoch-clone-setup.sql`: تنها در Clone موقت یک Schema مستقل `medtour_control`، جدول `tenant_epochs`، نقش `mt_control_reader` فقط‌خواندنی و `mt_control_writer` با دسترسی محدود به تغییر `generation`/`enabled` می‌سازد. Trigger اجازه کاهش یا تکرار نسل را نمی‌دهد. این دو Role به اطلاعات بیماران و جدول سراسری Tenants مجوز ندارند.
- `backend/tests/test_stage_19_23_multiworker_epoch.py`: تست Unit دو Worker مجزا با وضعیت Epoch مشترک، قطع Control Plane، عدم پذیرش نسل قدیمی، حفظ Tenant دوم و تخلیه Leaseهای شروع‌شده.
- `scripts/rls-multiworker-epoch-probe.py`: آزمون دو Worker و سه نقش کنترلی/کاربردی روی PostgreSQL 17 ایزوله؛ Credentialهای مدیریتی کنترل فقط در همین Probe وجود دارند و هرگز وارد Runtime HTTP عملیاتی نشده‌اند.
- `scripts/rls-multiworker-epoch-clone-test.ps1`: اجرای موقت `docker network --internal` با دیتابیس ساختگی، بدون تماس با Volume/Compose فعال.

### مسیر کنترل

```text
Worker A / Worker B
  └─ incoming request (previously authenticated)
      └─ trusted local Tenant registration + expected generation
          └─ PostgreSQL control reader (read-only)
              └─ current generation + enabled?
                  ├─ yes → lease on tenant-specific low-privilege LOGIN (RLS)
                  ├─ disabled/stale → retire local pool; deny new lease
                  └─ control unavailable → deny new lease; NEVER fallback
```

## اجرای Windows PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -EpochControlOnly
& .\scripts\rls-multiworker-epoch-clone-test.ps1
```

در صورت موفقیت آزمون Clone:

```text
PASS: STAGE 19.23 ISOLATED MULTIWORKER TENANT EPOCH REVOCATION TEST COMPLETED
```

برای اطمینان از عدم رگرسیون می‌توان `-FullSuite` را نیز اجرا کرد.

**دقت در دامنه آزمون:** اسکریپت Clone، دو Registry مستقل را در یک Process پایتون با دو Engine خواندن کنترل مرکزی ایجاد می‌کند و ابطال را در PostgreSQL واقعی می‌آزماید. این آزمون هنوز جایگزین آزمایش واقعی چند Process/Pod، قطع ارتباط شبکه و مدیریت ظرفیت سراسری نیست.

## مرزهای امنیتی و محدودیت‌های باقی‌مانده

1. **ابطال و درخواست در حال اجرا:** تأیید Epoch در لحظه اخذ Lease است؛ درخواست‌هایی که پیش‌تر Lease گرفته‌اند اجازه دارند تا پایان اجرا شوند. بین آخرین خواندن Epoch و ثبت آن در Control Plane رقابت کوتاهی وجود دارد. این طراحی «قطع فوری تمام درخواست‌های در حال اجرا» نیست.
2. **مقیاس:** هر Lease مستلزم Query مرکزی است؛ از آنجا که نتیجه Cache نمی‌شود، Latency، Availability و بار DB باید قبل از Production زیر Load Test اندازه‌گیری شود.
3. **چرخش Credential:** افزایش Generation فقط مانع استفاده از Pool نسل قدیمی می‌شود؛ Credential، Password، Role و Sessionهای قبلی PostgreSQL به‌صورت خودکار Rotation/REVOKE یا Terminate نمی‌شوند. این عملیات با Secret Manager، Provisioner مستقل و تأیید Admin باید جداگانه پیاده‌سازی و آزموده شوند.
4. **کنترل محرمانگی:** Credential خواندن مرکزی جدا از Credential Tenant است. Role نوشتن مرکزی در این Probe تنها برای شبیه‌سازی Admin به Docker موقت داده می‌شود؛ هرگز نباید در Process سرویس HTTP قرار بگیرد.
5. **همه Workerها باید از Wrapper استفاده کنند:** اتصال مستقیم به Registry محلی می‌تواند بررسی Epoch را دور بزند. دسترسی داخلی Runtime باید در معماری نهایی محصور و به‌صورت تست‌شده Enforce شود.
6. **ماندگاری و استقرار:** این‌ها فایل آزمایشی هستند. `main.py`، `get_db`، Alembic، Docker Compose و پایگاه اصلی تغییر نکرده‌اند؛ Migration واقعی، توکن‌های قدیمی، Bootstrap، WhatsApp PHI Processing و Privacy Notice هنوز باز هستند.

**موفقیت آزمایش این مرحله اثبات کامل چرخش Credentialهای Production یا گواه آماده‌بودن برای پردازش PHI نیست.**
