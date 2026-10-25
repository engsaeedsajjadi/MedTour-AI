# بخش ۱۷ — هماهنگی ویزای درمانی (Medical Visa Coordination)

**وضعیت:** پیاده‌سازی گردش‌کار داخلی و تست‌های ساختگی؛ اتصال به دولت، سفارت، مرکز رسمی صدور ویزا، اعتبارسنجی مدارک، و استفاده از اطلاعات واقعی بیمار **وجود ندارد**.

## دامنه
- ثبت درخواست idempotent برای پرونده (tenant + case + request_key) با کشور مبدأ ISO2 و مقصد IR.
- فعال بودن رضایت مستقل `visa_coordination` و `intake` قبل از خواندن، ثبت و تغییر. صدور لینک رضایت یک‌بارمصرف در `/api/v1/consent-links/{patient_id}/visa_coordination` از سرویس مشترک.
- فهرست نمونه ۴ موردی مدارک برای پیگیری **داخلی**؛ نه تأیید اصل گذرنامه یا فهرست رسمی الزامات کنسولی. اپراتور دریافت/نیازمند اصلاح را ثبت می‌کند؛ فقط مدیر می‌تواند بررسی داخلی مدارک را با مرجع غیردرخور افشای PII ثبت کند.
- گردش: `requested → in_review → ready_for_manual_submission → submission_reported → outcome_reported`؛ مورد درخواست مدارک تکمیلی به `in_review` برمی‌گردد. لغو اداری و مسدودسازی رضایت نیز پیاده شده‌اند.
- ارسال و نتیجه با *مرجع واردشده توسط مدیر* ثبت می‌شوند. هیچ تماس با API دولت انجام نمی‌شود؛ `official_visa_issued_verified=false` همیشه صریح است.
- ثبت Audit، CaseTimeline و رویداد append-only با کلید گام idempotent و محافظت در برابر replay متفاوت.
- صف پیگیریِ دارای مهلت، tenant-scoped و بدون ارسال پیام خودکار، با محدودیت تعداد.
- بدون ذخیره شماره پاسپورت، تصویر پاسپورت، تاریخ تولد، عنوان بیماری یا متن آزاد در این ماژول.
- لغو رضایت `intake`، `medical_documents` یا `visa_coordination` درخواست‌های باز را در تراکنش اصلی `blocked` می‌کند. رضایت جدید درخواست قبلی را باز نمی‌کند؛ درخواست جدید لازم است.
- مسیر عمومی قدیمی `/api/v1/travel` همچنان اجازه ثبت درخواست قدیمی دارد، اما **تأیید وضعیت visa** از آن مسدود است. مدل عمومی `Operation(kind=visa)` همچنان ثبت عملیاتی غیرکنسولی است و سند صدور ویزا محسوب نمی‌شود.

## API
- `POST /api/v1/visa-coordination/cases/{id}/applications`
- `GET /api/v1/visa-coordination/cases/{id}/applications`
- `POST /api/v1/visa-coordination/applications/{id}/checklist`
- `POST /api/v1/visa-coordination/applications/{id}/transition`
- `GET /api/v1/visa-coordination/applications/{id}/history`
- `GET /api/v1/visa-coordination/due`

## داده و UI
Migration: `a17e526a13c9` (پس از `a16b7d20f4ce`). جداول `medical_visas`، `medical_visa_checklist` و `medical_visa_events`. رابط فارسی: `/visa`.

## معیارهای پذیرش محیط توسعه
تست `backend/tests/test_section_17_visa.py`: کنترل نقش‌ها، رضایت، لغو رضایت از مسیر بیمار، عدم احیای درخواست قدیمی، ایزولاسیون tenant، idempotency، کامل‌بودن چک‌لیست، محدودیت مراحل و Audit، جلوگیری از تأیید ویزا از API قدیمی، عدم ادعای صدور/اتصال رسمی. در CI با PostgreSQL 17/Redis 7 Migration و Next.js TypeScript/build بررسی شود.

## گیت‌های باز برای استفاده تجاری واقعی
مجوز حقوقی و توافق با ارائه‌دهندگان رسمی خدمات ویزا، راستی‌آزمایی مستقل منابع و نتیجه، مجموعه مدارک درست برای کشور/تابعیت و شرایط روز، هویت‌سنجی معتبر بیمار، رضایت‌نامه قانونی نسخه‌بندی‌شده، امنیت اطلاعات و DLP، S3/KMS/virus scan، MFA/RLS، retention/erasure و ارزیابی امنیتی/حریم خصوصی مستقل. **این کد مجوز پرداخت، سفر، ورود یا صدور ویزا نیست.**
