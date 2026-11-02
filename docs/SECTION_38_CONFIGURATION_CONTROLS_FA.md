# بخش ۳۸ — Configuration Controls / مدیریت تنظیمات سازمانی

## تغییرات ثبت‌شده
- اعتبارسنجی سمت سرور برای کلید `feature_flags` با فهرست محدود `show_operations_summary`، `show_help_tips` و `compact_dashboard`. این‌ها فقط ترجیحات نمایشی هستند و نباید در تصمیم‌های اجازه دسترسی یا ارسال اطلاعات استفاده شوند.
- رد کردن Feature Flagهای ناشناخته یا امنیتی مانند `disable_rls` یا `enable_real_payments` با HTTP 422.
- اعتبارسنجی `enabled_languages` و `locale` برای زبان‌های `fa,en,ar,ps,prs` و جلوگیری از مقدار تکراری.
- محدودکردن `public_portal` به گزینه نمایشی `show_public_link`؛ این تنظیم قابلیت صدور session یا دسترسی اطلاعات بیمار را فعال نمی‌کند.
- حفظ RBAC مدیریت تنظیمات، فیلتر `tenant_id` و Audit موجود در `PUT /api/v1/settings/{key}`.
- بدون Migration جدید؛ ساختار ذخیره قبلی TenantSetting حفظ شده است.
- تست مصنوعی `backend/tests/test_section_38_configuration.py` برای عدم پذیرش تنظیمات خطرناک و جداسازی Tenant.

## تست
```powershell
git fetch origin
git switch feature/section-38-configuration-guards
cd backend
python -m pytest -q tests/test_section_38_configuration.py
```
این تست نوشته شده اما هنوز در این گفتگو اجرا نشده است.

## کارهای باقی‌مانده برای تکمیل واقعی بخش ۳۸
1. مدل نسخه‌دار تنظیمات و optimistic concurrency با جلوگیری از Lost Update بین مدیران.
2. تاریخچه تغییرات قابل بازیابی با ثبت diff ایمن، سیاست retention و audit غیرقابل‌تغییر.
3. فرایند تأیید دومرحله‌ای برای تنظیمات پرریسک و جداسازی نقش‌های تغییر‌دهنده/تأییدکننده.
4. Enforce قابلیت‌های تجاری و quota در backend service، نه صرفاً نمایش Frontend؛ اتصال امن به زیرسیستم اشتراک بخش ۳۷ پس از ادغام.
5. سیستم تنظیمات تایپ‌شده برای ساعات کاری، منطقه زمانی، قواعد اعلان و ارتباطات با کنترل رضایت.
6. محافظت از secrets در Secrets Manager نه در فیلد JSON تنظیمات، همراه با چرخش کلید و دسترسی محدود.
7. داشبورد فارسی کامل با validation و نمایش قابل فهم خطا، E2E چند Tenant و آزمون PostgreSQL RLS.

**حکم پذیرش:** این مرحله فقط جلوی تغییر خودسرانه برخی تنظیمات را می‌گیرد؛ به‌معنای آماده بودن SaaS یا تأیید استفاده از اطلاعات پزشکی واقعی نیست.
