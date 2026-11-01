# آمادگی تجاری MedTour-AI — رفع موانع عرضه

این سند تغییرات شاخه `integration/medtour-45-unified-candidate` برای رفع موانع عرضه تجاری و مراحل راه‌اندازی آن را توضیح می‌دهد.
موارد ۱ تا ۶ در کد حل شده‌اند. مورد ۷ تصمیم حقوقی است و کد فقط جلوی استفاده با بیمار واقعی را تا ثبت آن تصمیم‌ها می‌گیرد.

## ۱. جداسازی سازمان‌ها در پایگاه داده (RLS)

- نقش جدید `medtour_app` با `NOSUPERUSER NOBYPASSRLS` ساخته می‌شود و فقط دسترسی خواندن و نوشتن داده دارد.
- روی هر ۸۸ جدول دارای `tenant_id`، `ENABLE` و `FORCE ROW LEVEL SECURITY` با سیاست `mt_tenant_isolation` فعال می‌شود.
- API در شروع هر تراکنش `app.tenant_id` را از هویت تأییدشده (JWT کارکنان، نشست پرتال بیمار، لینک رضایت و ...) تنظیم می‌کند. پیش‌فرض «هیچ سازمانی» است، پس کوئری‌ای که فیلتر سازمان را فراموش کند، داده سازمان دیگر را نمی‌بیند.
- مقدارها با `set_config(..., true)` فقط برای همان تراکنش تنظیم می‌شوند و از طریق connection pool به درخواست بعدی نشت نمی‌کنند.
- جست‌وجوهای پیش از احراز هویت (توکن refresh، چالش MFA، دعوت پرتال، توکن پرتال) فقط با `system_scope` و صرفاً برای پیدا کردن سازمان صاحب توکن انجام می‌شوند.
- API در حالت `RLS_ENFORCEMENT=required` (پیش‌فرض docker compose) یا `APP_ENV=production`، اگر با نقش ممتاز وصل شده باشد یا RLS کامل نباشد، **اجرا نمی‌شود**.

## ۲. تست دو سازمان واقعی

- `tests/test_tenant_rls_isolation.py` روی PostgreSQL واقعی با نقش `medtour_app` اجرا می‌شود.
- این تست‌ها بیمار، پرونده، سند، پیش‌فاکتور، نوبت، پرتال بیمار و refresh را بین دو سازمان بررسی می‌کنند. یک کوئری بدون فیلتر سازمان را هم شبیه‌سازی می‌کنند و نشت connection pool را می‌سنجند.
- کل مجموعه تست موجود هم می‌تواند روی PostgreSQL و RLS اجرا شود:

```bash
MEDTOUR_TEST_PG='postgresql+psycopg://OWNER@HOST:PORT/DB' pytest
```

## ۳. Audit

- هر پاسخ 403 رویداد `access_denied` با مسیر، متد و نقش ثبت می‌کند.
- ورود موفق، ورود ناموفق (ایمیل ناشناخته فقط به‌صورت هش)، چالش MFA و کد اشتباه پرتال بیمار ثبت می‌شوند.
- ستون جدید `audit_events.detail` هیچ رمز، توکن یا محتوای پزشکی نگه نمی‌دارد.

## ۴. مخزن امن مدارک، اسکن بدافزار و نگهداری

```bash
docker compose --profile secure-storage up -d
```

این دستور MinIO (سازگار با S3، خصوصی و نسخه‌دار) و ClamAV را اجرا می‌کند. تنظیمات `.env`:

```
DOCUMENT_PROCESSING_APPROVED=true
MEDICAL_STORAGE_SELF_HOSTED=true
MEDICAL_S3_ENCRYPTION=client
MEDICAL_S3_ENDPOINT=http://minio:9000
MEDICAL_S3_BUCKET=medtour-medical
MEDICAL_MASTER_KEY=<32 بایت base64>
AWS_ACCESS_KEY_ID=... / AWS_SECRET_ACCESS_KEY=...
MINIO_ROOT_USER=... / MINIO_ROOT_PASSWORD=...
CLAMAV_HOST=clamav
MEDICAL_DOCUMENT_RETENTION_DAYS=3650
```

- هر فایل قبل از ذخیره با ClamAV اسکن می‌شود. هر نتیجه‌ای غیر از OK فایل را رد می‌کند.
- هر سند کلید AES-256-GCM اختصاصی دارد. فقط نسخه رمزشده این کلید با `MEDICAL_MASTER_KEY` در پایگاه داده نگه داشته می‌شود و MinIO فقط متن رمزشده را می‌بیند.
- **حذف رمزنگاری‌شده:** مدیر با شماره مرجع، سند لغوشده یا سندی که دوره نگهداری‌اش تمام شده را حذف می‌کند. این کار کلید و فایل را از بین می‌برد و سند در هیچ نسخه پشتیبانی هم قابل بازیابی نیست.
- **توقیف قانونی:** سند در توقیف حذف نمی‌شود.
- مسیر AWS S3 با KMS (`MEDICAL_S3_ENCRYPTION=kms`) همچنان پشتیبانی می‌شود.

## ۵. احراز هویت

- **کد ورود بیمار:** با `OTP_DELIVERY_PROVIDER=email` (SMTP) یا `sms_webhook` (آداپتور پیامک)، لینک و کد مستقیماً به ایمیل یا موبایل ثبت‌شده بیمار ارسال می‌شود. کارمند فقط پیام «ارسال شد به p***@...» را می‌بیند. خارج از development، بدون ارسال‌کننده تأییدشده، ورود بیمار غیرفعال است.
- **ورود دومرحله‌ای کارکنان:** برای نقش‌های `admin` و `operator` اجباری است (`STAFF_MFA_REQUIRED=true` و `STAFF_MFA_ROLES=admin,operator`). در production این دو نقش همیشه اجباری‌اند و فهرست فقط قابل گسترش است. کاربری که فقط رمز زده، فقط به صفحه فعال‌سازی TOTP دسترسی دارد. به `MFA_ENCRYPTION_KEY` نیاز است.

## ۶. نوبت‌دهی

- نوبت «تأیید داخلی» قابل لغو است و ظرفیت آزاد می‌شود.
- لغو ظرفیتی که نوبت فعال دارد رد می‌شود، مگر با `?cancel_appointments=true` که همه نوبت‌های داخل آن را لغو و ثبت می‌کند.
- تأیید نوبت پس از لغو ظرفیت آن رد می‌شود.
- وضعیت مسیر قدیمی `/appointments` با تقویم هماهنگ است و آن مسیر دیگر اجازه رزرو هم‌پوشان نمی‌دهد.

## ۷. الزامات حقوقی (خارج از کد)

با `REAL_PATIENT_DATA_MODE=true` سامانه فقط وقتی اجرا می‌شود که همه کنترل‌های فنی بالا فعال باشند و این مراجع ثبت شده باشند:

| متغیر | تصمیمی که باید گرفته شود |
| --- | --- |
| `PUBLIC_PRIVACY_NOTICE_URL` و `PRIVACY_NOTICE_VERSION` | متن نهایی اطلاعیه حریم خصوصی، منتشرشده روی HTTPS |
| `PRIVACY_NOTICE_APPROVAL_REFERENCE` | تأیید وکیل یا مسئول حفاظت داده بر آن متن |
| `DATA_PROTECTION_REVIEW_REFERENCE` | بررسی قوانین داده سلامت در ایران، افغانستان و کشورهای عربی هدف، و انتقال داده بین‌مرزی |
| `PROVIDER_CONTRACTS_REFERENCE` | قرارداد و ارزیابی ارائه‌دهندگان هوش مصنوعی، پیام‌رسان، پرداخت، ایمیل یا پیامک و ذخیره‌سازی |
| `MEDICAL_TOURISM_LICENSE_REFERENCE` | مجوزهای فعالیت تسهیلگری گردشگری سلامت |

وضعیت لحظه‌ای این چک‌لیست در صفحه «ممیزی جداسازی سازمان‌ها» و در `GET /api/v1/compliance/readiness` دیده می‌شود.

## نتیجه آزمون‌ها

- کل مجموعه تست روی PostgreSQL 16 با نقش `medtour_app` و RLS اجباری: ۴۹۲ موفق، ۰ ناموفق.
- همان مجموعه روی SQLite: ۴۸۷ موفق، ۰ ناموفق.
- اجرای مهاجرت‌ها روی پایگاه خالی: ۸۸ از ۸۸ جدول دارای RLS اجباری؛ API با حساب owner اجرا **نمی‌شود** و با `medtour_app` اجرا می‌شود.

## راه‌اندازی روی نصب موجود

1. به `.env` اضافه کن: `APP_DB_PASSWORD=<۱۶+ حرف و عدد>`، `RLS_ENFORCEMENT=required`، و برای ورود دومرحله‌ای `MFA_ENCRYPTION_KEY=<خروجی دستور زیر>`:

```bash
python -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

2. اجرا کن: `docker compose up -d --build migrate api web`. سرویس `migrate` مهاجرت‌ها را اجرا می‌کند و `app.provision_db` نقش `medtour_app` را فعال می‌کند.
3. در صفحه «ممیزی جداسازی سازمان‌ها» باید «نقش دیتابیس غیرممتاز: بله» دیده شود.
4. بررسی مستقیم:

```bash
docker compose exec -T db psql -U medtour -d medtour -c "select usename from pg_stat_activity where datname='medtour'"
```

اتصال‌های API باید با `medtour_app` باشند.
