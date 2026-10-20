# مرحله ۱۹.۱۷ — Token-to-Tenant Routing امضاشده (Staged / غیرفعال)

**تاریخ: ۲۰ اکتبر ۲۰۲۶ — وضعیت: کد و تست در مخزن ثبت شده؛ آزمایش سیستم کاربر هنوز دریافت نشده است.**

## مسئله حل‌شونده

بعد از آزمون موفق ۱۹.۱۶ (FastAPI + PostgreSQL RLS، نقش‌های `mt_clone_a` و `mt_clone_b` در محیط ایزوله)، مشکل اساسی فرآیند عملیاتی انتخاب Tenant پیش از دسترسی به داده است. نسخه کنونی سه توکن رمزنگاری‌نشده از نظر Tenant دارد:

- **Refresh:** یک توکن تصادفی `token_urlsafe(48)` که SHA-256 آن در `refresh_sessions.refresh_hash` ذخیره می‌شود؛ استخراج Tenant مستلزم Lookup در همان جدول است.
- **Portal:** توکن تصادفی لینک بیمار با هش ذخیره‌شده در `portal_access.token_hash`.
- **Consent:** توکن یک‌بارمصرف با هش ذخیره‌شده در `patient_consent_challenges.token_hash`.

این مدل با اتصال مشترک مدیریتی کار می‌کند، اما پس از اجبار RLS و نقش مستقل برای هر Tenant، نمی‌توان بدون تشخیص اولیه Tenant کوئری سراسری انجام داد.

## مرحله تحویل‌شده

ماژول `backend/app/tenant_route_tokens.py` به صورت جداگانه افزوده شده است. فعلاً هیچ endpoint، سرویس یا متغیر محیطی عملیاتی به این ماژول وصل نیست.

قالب توکن پیشنهادی جدید:

```text
mt1.<key-id>.<purpose>.<tenant-uuid>.<unix-expiry>.<random-256-bit>.<hmac-sha256>
```

- مقادیر `purpose` فقط `refresh`، `portal` یا `consent` هستند.
- UUID و زمان انقضا همراه کل داده‌های توکن با HMAC-SHA256 امضا می‌شوند؛ دستکاریِ Tenant یا زمان انقضا باعث رد شدن توکن می‌شود.
- بخش تصادفی از `secrets.token_urlsafe(32)` تولید می‌شود (۲۵۶ بیت تصادف قبل از Base64url).
- `kid` قابل چرخش است و Keyring می‌تواند کلید قدیمی را موقتاً برای اعتبارسنجی نگه دارد.
- حد بالای TTL در مرحله صدور و تفسیر: ۷ روز Refresh، ۲ ساعت Portal و ۳۰ دقیقه Consent.
- طول توکن حداکثر ۲۰۰ کاراکتر؛ با Field فعلی Refresh سازگار است.
- هش **تمام توکن** همچنان SHA-256 است و در ستون‌های موجود به‌عنوان credential lookup قابل ذخیره می‌ماند.
- Hint فقط برای انتخاب Tenant Pool کاربرد دارد، **نه احراز هویت یا اجازه دسترسی**. بعد از انتخاب Pool، توکن کامل باید از نظر وجود Hash، Tenant، انقضا، لغو و Replay روی پایگاه‌داده همان Tenant بررسی شود.

## امنیت و محدودیت

1. **توکن قدیمی:** ورودی‌های Legacy هیچ Tenant Hint معتبری تولید نمی‌کنند. پیش از فعال‌سازی مدل جدید باید Migration/Sunset انجام شود؛ امکان تعویض ناگهانی Credential روی API زنده وجود ندارد. دوره ۷روزه Refresh را در برنامه انتقال لحاظ کنید.
2. **Secret اختصاصی:** کلیدهای Keyring تصادفی حداقل ۳۲ بایت و مستقل از `JWT_SECRET` هستند؛ در Secret Manager نگه‌داری می‌شوند. برای محیط عملیاتی نباید از کلیدهای ثابت آزمون استفاده کرد.
3. **حمل توکن:** Portal/Consent/Refresh همچنان Bearer Credential هستند؛ نشت توکن مساوی خطر دسترسی تا انقضا/لغو است. صفحه `consent-links/preview?token=...` ممکن است توکن را در history، لاگ Reverse Proxy و Referer افشا کند؛ حذف توکن از Query String و استفاده از POST یا Header محافظت‌شده باید جداگانه طراحی و تست شود.
4. **مسیر‌یابی احراز هویت:** JWT باید قبل از استفاده از Claim `tid` امضای معتبر داشته باشد؛ Tenant Slug هنگام Login یک نامزد است، نه اثبات هویت؛ Webhook ابتدا باید امضای Meta را بررسی کند.
5. **هم‌زمانی و تغییر رمز:** ساخت امن Pool و نگاشت `tenant_id → DB role/secret`، چرخش نقش‌ها، احراز هویت اصلی و Refresh Replay در حضور درخواست هم‌زمان هنوز باقی است.
6. **RLS عملیاتی:** این ماژول Policy، FK و `get_db` را روی محیط زنده تغییر نمی‌دهد؛ RLS و DB Role واقعی هنوز روی API عملیاتی فعال نشده‌اند.

## تست‌ها

`backend/tests/test_stage_19_17_tenant_route_tokens.py` شامل تست‌های صدور، تاریخ انقضا، جداسازی هدف، UUID غیرمجاز، جعل هر بخش از توکن، Nonce، هش ذخیره‌سازی، حذف کلید قدیمی و Key Rotation است. این‌ها آزمون‌های Unit هستند، نه Integration روی PostgreSQL.

## اجرای تست در Windows PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -TokenRoutingOnly
# After the targeted checks pass, run the complete suite:
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
```

ابتدا تست‌های اختصاصی ۱۹.۱۷ اجرا می‌شوند و سپس مجموعه کامل شامل ۵۴ تست پیشین به‌علاوه تست‌های جدید باید اجرا شود. تا دریافت خروجی کاربر، این مرحله «آماده آزمایش» است.

## مراحل بعدی قبل از مهاجرت

- طراحی Credential-Resolver با کمترین دسترسی برای انتقال Legacy Token، یا خاتمه کنترل‌شده توکن‌های قدیمی؛ عدم استفاده از Superuser Registry در HTTP Runtime.
- ادغام اختیاری و آزمایشی با صدور و مصرف Refresh/Portal/Consent همراه تست PostgreSQL اصلی **در Clone**؛ سپس طراحی مهاجرت بدون قطع خدمات.
- طراحی per-Tenant Pool/Secret Manager/Bootstrap/Alembic و تست امنیت واقعی مسیر Login/Health/Webhook.
- تست‌های شکست Resolver، Duplicate Token، Replay تحت هم‌زمانی، Secret Rotation، Fail-closed و Load.
- بعد از تأیید نهایی Security Review و تست Rollback/Backup، بررسی جداگانه استقرار عملیاتی.
