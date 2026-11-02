# بخش ۳۲ — Database Architecture و امنیت چندمستأجری

## وضعیت تحویل
ابزار خواندنی و بدون تغییر داده برای ممیزی ساختار PostgreSQL آماده شده است. **تکمیل RLS تولیدی، انتقال دیتابیس قدیمی و تأیید امنیت Enterprise انجام نشده است.** این تحویل یک مرحله قابل‌اندازه‌گیری است، نه گواهی Production.

## کنترل‌های موجود
- PostgreSQL 17 و SQLAlchemy/Alembic، نسخه‌بندی migrations
- مدل‌های دارای tenant_id و قیود FK مرکب از بخش ۲۶
- سیاست principal-based RLS از قبل آماده شده، اما عمداً روی DB عملیاتی فعال نیست
- Guard برای جلوگیری از استفاده از نشست مشترک در strict tenant mode
- تست‌های isolated PostgreSQL clone از بخش ۲۶

## قابلیت جدید بخش ۳۲
- `backend/app/db_schema_audit.py`: بررسی از کاتالوگ PostgreSQL و بدون خواندن اطلاعات بیمار
- شمارش جدول‌های tenant-owned؛ گزارش RLS ENABLE/FORCE، سیاست mt26_principal_isolation، UNIQUE(tenant_id,id)
- بررسی وجود FKهای مرکب tenant-aware در کنار رابطه‌های تک‌ستونی موجود
- هر نقص گزارش را fail-closed می‌کند؛ حتی گزارش بدون نقص نیز به معنای تأیید routing زمان اجرا نیست
- `backend/scripts/section32_audit.py`: اجرا فقط با `MEDTOUR_SYNTHETIC_CLONE=1` و اتصال PostgreSQL read-only به پایگاه تستی/بازیابی‌شده؛ هیچ دستور ALTER/UPDATE/DELETE اجرا نمی‌شود
- `backend/tests/test_section_32_database_audit.py`: تست تحلیل schema ناقص و حالت‌های fail-closed

## اجرای تست نرم‌افزاری
```powershell
git fetch origin
git switch feature/section-32-database-audit
docker compose up -d --build
docker compose exec api pytest -q tests/test_section_32_database_audit.py
```

## ممیزی دیتابیس Clone با کاربر فقط خواندنی
در محیط آزمایش، `SCHEMA_AUDIT_DATABASE_URL` را به DSN حساب catalog-reader روی یک PostgreSQL clone تنظیم کنید (هرگز credentials را در چت/گیت قرار ندهید)، سپس:
```powershell
$env:MEDTOUR_SYNTHETIC_CLONE="1"
python -m scripts.section32_audit
```
دستور بالا را از پوشه `backend` و با `SCHEMA_AUDIT_DATABASE_URL` تنظیم‌شده اجرا کنید. خروجی JSON، وضعیت جدول‌ها را بدون افشای داده‌های پرونده نشان می‌دهد.

## الزامات باقی‌مانده طبق پرامپت
1. بررسی همه جداول در نسخه نهایی و اعمال FKهای مرکب و NOT VALID/VALIDATE امن برای داده‌های قدیمی.
2. اجرای طرح Expand/Backfill/Validate/Contract همراه snapshot، برنامه rollback و کنترل lock/timeouts.
3. راه‌اندازی حساب DB حداقل‌دسترسی مخصوص Tenant و اعمال FORCE RLS فقط پس از آزمون همه مسیرهای احراز هویت، پرتال، وب‌هوک و Worker.
4. تست مستقل PostgreSQL برای جلوگیری از دسترسی افقی، transaction pooling/session leakage و race condition.
5. Migration rollback، backup/PITR، تست Restore و پایش bloat/slow queries/indexes در محیط واقعی.
6. آلارم migration drift، سازگاری Alembic با همه مدل‌ها و CI staging.
7. ارزیابی امنیت، رمزنگاری در حالت سکون و حمل، چرخش secrets و ممیزی privacy قبل از داده واقعی بیمار.

## محدودیت مهم
Audit کاتالوگ جایگزین آزمون اجرای واقعی policy، تست penetration و تأیید هویت DB principal نیست. روی پایگاه عملیاتی RLS را به‌صورت خودکار فعال نکنید.
