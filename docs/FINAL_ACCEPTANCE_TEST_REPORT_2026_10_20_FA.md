# گزارش نهایی پذیرش آزمون‌ها — MedTour-AI

**تاریخ تنظیم:** ۲۰ اکتبر ۲۰۲۶  
**مخزن:** `engsaeedsajjadi/MedTour-AI`، شاخه `main`  
**بازه توافق‌شده:** مراحل ۱۹.۱۱ تا **۱۹.۲۳**  
**نتیجه:** **پذیرش آزمون‌های توسعه و امنیتی ایزوله — PASS**؛ **آمادگی Production/PHI تأیید نشده است**.

## ۱. شواهد موفقیت

### اعلام‌شده توسط کاربر در همین فرآیند

- `PASS: STAGE 19.20 ISOLATED REQUEST-BOUND FASTAPI TENANT ROUTING TEST COMPLETED`
- `PASS: STAGE 19.21 PREAUTH FAIL-CLOSED UNIT TESTS COMPLETED`؛ در اجرای گزارش‌شده `8 passed, 1 warning`
- `PASS: STAGE 19.21 ISOLATED PREAUTH LOGIN REFRESH WEBHOOK ROUTING TEST COMPLETED`
- `PASS: STAGE 19.22 TENANT REGISTRY LEASE AND REVOCATION UNIT TESTS COMPLETED`
- `PASS: STAGE 19.22 ISOLATED TENANT POOL REGISTRY LIFECYCLE TEST COMPLETED`
- `PASS: STAGE 19.23 ISOLATED MULTIWORKER TENANT EPOCH REVOCATION TEST COMPLETED` (پس از اجرای مجدد نهایی نیز تأیید شد)
- `PASS: FULL SYNTHETIC BACKEND TEST SUITE COMPLETED IN OFFLINE CONTAINER` (آخرین خروجی کاربر)

### نتایج پیشین ثبت‌شده در جریان توسعه

- ۱۹.۱۱: آزمون ۴۸ FK مرکب Tenant روی Clone موفق گزارش شد.
- ۱۹.۱۲ تا ۱۹.۱۳: ۳۷ جدول دارای سیاست RLS روی Clone و مقاومت در برابر جعل GUC/Principal آزمایش شدند.
- ۱۹.۱۴ تا ۱۹.۱۶: مسیر‌یابی Tenant به نقش دیتابیس و مرزهای احراز هویت/FastAPI در Clone آزمایش شدند.
- ۱۹.۱۷: توکن‌های مسیر‌یابی دارای HMAC، مقصد و انقضا با Unit Test.
- ۱۹.۱۸: Lookup مبتنی بر Hash Credential تحت RLS.
- ۱۹.۱۹: عملیات اتمیک Refresh/Consent در Clone با آزمون Replay.
- ۱۹.۲۰ تا ۱۹.۲۳: تکمیل تست‌های Request Routing، Pre-auth، Lease/Revocation، Shared Epoch و Fail-Closed.

**روش ارزیابی:** این گزارش بر اساس پیام‌های PASS ارسال‌شده و بررسی فایل‌های کنونی مخزن است؛ فایل کامل Log، تعداد دقیق همه تست‌های FullSuite و گزارش CI مستقل دریافت نشده‌اند. بنابراین ادعای درصد پوشش آزمون، نبود آسیب‌پذیری یا موفقیت روی محیط واقعی ندارد.

## ۲. محدوده اثبات‌شده

- جداسازی Tenantها در PostgreSQL با **نقش‌های Login غیرممتاز** و ۳۷ سیاست RLS **روی Clone ایزوله**.
- تأیید `session_user` و نگاشت خصوصی Role→Tenant پیش از قرار دادن Pool در اختیار سرویس.
- رد Cross-Tenant Lookup، Refresh Replay، درخواست‌های بدون Credential معتبر و Webhook Meta فاقد امضای معتبر یا حساب مجاز.
- احراز حداقل دسترسی Pool، سقف تعداد اتصال و Lease؛ جلوگیری از استفاده از Session پس از پایان Lease؛ ابطال Tenant و Draining.
- کنترل مرکزی Epoch بین **دو Registry مستقل در یک Process آزمایشی** با PostgreSQL مشترک، رد درخواست تازه بعد از تغییر Epoch و Fail-Closed هنگام قطع کنترل.
- اجرای **Full Synthetic Backend Test Suite** در کانتینر Offline روی کد Check-out‌شده.

## ۳. مواردی که عمداً تأیید نمی‌شوند (مانع تحویل Production)

مطابق بررسی فایل‌های شاخه `main` در ۲۰ اکتبر ۲۰۲۶:

1. `backend/app/main.py` همچنان از `Depends(get_db)` عملیاتی استفاده می‌کند؛ مسیر `backend/app/staged_preauth_service.py`، `staged_tenant_epoch_control.py` و Registry مرحله‌ای به Runtime اصلی وصل نشده‌اند.
2. `backend/app/database.py` همچنان `get_db` مشترک ارائه می‌کند؛ Connection Routing مبتنی بر Tenant/Role در مسیر اصلی مهاجرت نکرده است.
3. `backend/app/session_api.py` همچنان منطق قبلی Refresh را دارد؛ مهاجرت توکن‌های موجود و سیاست گذار امن هنوز نیازمند طراحی عملیاتی است.
4. `backend/app/whatsapp.py` همچنان Tenant را از `Tenant.slug` می‌خواند. آداپتور Meta مرحله‌ای صرفاً Route را اعتبارسنجی می‌کند؛ پردازش واقعی پیام با RLS، Consent، Idempotency، Privacy و Human Review در API واقعی اثبات نشده است.
5. RLS/Composite FK، Provisioning مرکزی، مدیریت Secret/Role و برنامه Rollback هنوز به Alembic و دیتابیس اصلی اعمال نشده‌اند؛ تست Clone معادل Migration واقعی نیست.
6. تأیید دو Worker آزمایشی در یک Process جایگزین تست اجرای واقعی Multi-Process/Pod، Failover و Load Test نمی‌شود.
7. مراحل عملیاتی مانند Secrets Manager، چرخش رمز، مانیتورینگ/Alert، Disaster Recovery، بازیابی Backup، قوانین نگهداری PHI و ممیزی امنیت مستقل هنوز به آزمون پذیرش Production نیاز دارند.

## ۴. وضعیت مرحله ۱۹.۲۴

مرحله ۱۹.۲۴ پس از سقف توافق‌شده تعریف شده است. فایل‌های تست و اسکریپت مربوط به چرخش رمز PostgreSQL در GitHub موجودند، ولی **اجرای موفق تست یکپارچگی ۱۹.۲۴ توسط کاربر تأیید نشده است**. این مرحله **شرط بسته‌شدن پذیرش آزمون‌های ۱۹.۱۱ تا ۱۹.۲۳ نیست**. اجرای `-FullSuite` ممکن است Unit Testهای مرتبط را هم شامل شده باشد؛ این معادل آزمایش چرخش رمز در PostgreSQL نیست.

## ۵. نتیجه و تصمیم

| موضوع | تصمیم |
|---|---|
| بسته آزمون‌های توافق‌شده تا ۱۹.۲۳ | **PASS / بسته شد** |
| آزمون رگرسیون Backend در کانتینر Offline | **PASS** |
| آزمون نهایی PostgreSQL/RLS در Clone | **PASS** |
| اعلام عدم وجود نقص امنیتی | **انجام نمی‌شود** |
| مجوز استقرار Production یا پردازش PHI واقعی | **صادر نمی‌شود** |
| افزودن مراحل شماره‌دار جدید به توافق | **خیر** |

**نتیجه نهایی:** مرحله تست و ممیزی امنیتی *ایزوله* مطابق محدوده توافق پایان یافته است. برای استفاده با بیمار واقعی، به‌جای ادامه شماره‌گذاری تست‌ها، یک پروژه مشخص «مهاجرت عملیاتی/Go-Live» با پذیرش مستقل، مالک اجرایی، معیار Rollback و تأییدهای قانونی/امنیتی لازم است.

### دستورات قابل تکرار

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
# فقط با Backup ساختگی و فاقد اطلاعات بیمار واقعی:
& .\scripts\rls-multiworker-epoch-clone-test.ps1
```

**توجه:** گزارش بر مبنای شواهد ارسالی کاربر تهیه شده است و هیچ دستور تازه‌ای برای تغییر پایگاه داده اصلی تجویز نمی‌کند.
