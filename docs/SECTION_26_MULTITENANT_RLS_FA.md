# بخش ۲۶ — مرزبندی Tenant، قیود مرکب و آماده‌سازی امن PostgreSQL RLS

**وضعیت واقعی:** Migration قیود روابط بین سازمانی، آماده‌سازی سیاست RLS و تست‌های واقعی RLS در **دیتابیس مصنوعی و ایزوله** انجام شده است. **RLS در دیتابیس عملیاتی به‌صورت خودکار ENABLE نشده** و `app.database.get_db` هنوز با `DATABASE_URL` مشترک کار می‌کند. تا زمان انتقال همه مسیرهای ورود و کاربران، پرتال، Refresh، Webhook، صفحه عمومی و Worker به نقش‌های PostgreSQL مستأجر و حذف اتصال ممتاز، جداسازی سرتاسری و استفاده تجاری از اطلاعات بیماران **کامل نیست**. هیچ استقرار Production مجاز نیست.

## تغییرات بخش ۲۶

### ۱. Migration `a26d528e91c4`

مهاجرت فرزند `a25e720d9b10` است و در تراکنش Alembic و با قفل محدود انجام می‌شود.

- جدول‌های Tenantدار از کاتالوگ واقعی PostgreSQL شناسایی می‌شوند، نه یک عدد ثابت یا فهرست ناقص. در CI با آخرین مدل پروژه **۸۲ جدول** گزارش شد.
- همه FKهای تک‌ستونی بین دو جدول Tenantدار شناسایی و پیش از ساخت قید جدید به‌صورت مستقیم با داده‌های موجود تطبیق داده می‌شوند. در CI **۱۷۳ رابطه** شناسایی شد. هر ردیف ناسازگار با Tenant دیگر باعث **لغو Migration** می‌شود، نه حذف/اصلاح خودکار داده.
- در هر جدول Tenantدار، کلید یکتای `(tenant_id,id)` و برای هر FK، قید متناظر `FOREIGN KEY (tenant_id,child_fk) REFERENCES parent (tenant_id,id)` اضافه می‌شود. FKهای قبلی حذف نمی‌شوند و رفتار قدیمی حذف/به‌روزرسانی حفظ می‌شود؛ FK اضافه‌شده `DEFERRABLE INITIALLY DEFERRED` است تا نتیجه نهایی تراکنش بررسی شود.
- نگاشت محرمانه `medtour_principal_private.role_tenant_mapping` و تابع `tenant_for_login()` ایجاد می‌شود. این تابع `SECURITY DEFINER` است، `session_user` واقعی PostgreSQL را به Tenant وصل می‌کند و به GUC قابل جعل `medtour.tenant_id` متکی نیست. دسترسی عمومی به تابع و جدول نگاشت لغو می‌شود.
- سیاست `mt26_principal_isolation` با `USING` و `WITH CHECK` برای همه جدول‌های Tenantدار **تعریف** می‌شود، ولی عمداً `ENABLE ROW LEVEL SECURITY` / `FORCE ROW LEVEL SECURITY` روی دیتابیس فعلی اجرا نمی‌شود، چون API و ورود قدیمی از یک کاربر مشترک PostgreSQL استفاده می‌کنند.
- نقش تازه‌ای به‌طور خودکار ساخته نمی‌شود و به API مشترک هیچ مجوزی داده نمی‌شود؛ ایجاد نقش و ثبت نگاشت مستلزم Provisioning امن، Secret Manager، کنترل دسترسی، RLS و تست‌های مهاجرت مستقل است.

### ۲. CI PostgreSQL واقعی، بدون دست‌زدن به DB توسعه

`backend/tests/section_26_pg_probe.py` فقط وقتی `CI=true`، `SECTION26_ISOLATED_PROBE=synthetic_only` و نام دیتابیس `medtour_ci` روی localhost باشد اجرا می‌شود. GitHub Actions این probe را در PostgreSQL 17 موقت اجرا می‌کند و روی جدول‌های مصنوعی RLS را فعال می‌سازد؛ این فعال‌سازی در دیتابیس کاربر یا محیط واقعی انجام نمی‌شود.

در آزمایش ایزوله:
- دو LOGIN PostgreSQL واقعی و غیر SUPERUSER/NOBYPASSRLS، هرکدام با اتصال مستقل و نگاشت Tenant محافظت‌شده ساخته می‌شوند؛
- `FORCE ROW LEVEL SECURITY` برای همه جدول‌های Tenantدار فعال می‌شود؛
- خواندن سطر سازمان دیگر در همه جدول‌ها، `INSERT` و `UPDATE` بین سازمان‌ها، جعل متغیر SQL و `SET ROLE`، دسترسی به جدول `tenants` و جدول محرمانه نقش‌ها آزمایش می‌شود؛
- افزودن پرونده با `tenant_id` خودی ولی `patient_id` متعلق به Tenant خارجی نیز باید **به‌خاطر FK مرکب** رد شود؛ پرونده با بیمار خودی باید مجاز باشد؛
- سرویس API موجود و کلیدهای دیتابیس کاربر دستکاری نمی‌شوند.

### ۳. گزارش واقعی آمادگی Runtime

`GET /api/v1/admin/tenant-isolation/status` فقط برای `admin` همان برنامه تعریف شده است. در PostgreSQL تعداد جدول‌ها، FKهای مرکب معتبر، Policyهای نصب‌شده، جدول‌های دارای FORCE RLS و محدودبودن DB role را گزارش می‌دهد.

- `verified_end_to_end_routing=false` و `production_ready=false` به‌صورت صریح تا زمان تست و ادغام تمام مسیرهای Runtime حفظ می‌شود.
- در unit-test SQLite وضعیت `not_postgresql` نمایش داده می‌شود؛ تست SQLite هیچ‌وقت به‌جای مدرک RLS حساب نمی‌شود.
- خروجی شامل رمز DB، DSN، نام کاربری PostgreSQL، شناسه Tenantهای دیگر یا Secretها نیست.

## فرایند پیشنهادی اجرای Migration روی دیتابیس توسعه

**پیش از اجرا روی DB دارای داده مهم حتماً backup قابل بازیابی تهیه کنید و برای مدتی توقف کوتاه سرویس را پیش‌بینی کنید.** قفل‌های ALTER TABLE و افزایش تعداد قیود و شاخص‌ها ممکن است روی دیتابیس‌های پرحجم زمان‌بر باشند. `lock_timeout` کوتاه باعث شکست امن Migration در زمان رقابت بالا می‌شود، نه اجرای نامحدود.

پس از نسخه پشتیبان:

```powershell
git pull origin main
docker compose up -d --build
docker compose exec api alembic current
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

گزارش را با حساب مدیر از `/api/v1/admin/tenant-isolation/status` بررسی کنید. انتظار دارید `rls_policy_tables` مثبت، `composite_tenant_fks` معتبر و `rls_force_tables=0` باشد. `production_ready=false` باید باقی بماند.

**هیچ دستور ENABLE RLS روی DB اصلی در این مرحله صادر نکنید.**

## معیارهای تکمیل‌نشده برای RLS سرتاسری Production

1. Provisioning رسمی نقش LOGIN مستقل لكل Tenant، نگه‌داری Password در Secret Manager، اعتبارسنجی نقش غیر‌مالک/NOBYPASSRLS و Revocation/Rotation همراه epoch و بار چند Worker.
2. اتصال همه مسیرهای HTTP از جمله login و refresh و opaque consent/portal، URLهای عمومی و وب‌هوک امضاشده به Pool مناسب پیش از هر Query؛ هیچ fallback به نقش مشترک یا DBA وجود نداشته باشد.
3. تعویض `get_db` واقعی، Worker و jobهای زمان‌بندی‌شده با factoryهای Tenant scoped؛ جداکردن کنترل‌پلین و وظایف مهاجرت.
4. RLS `ENABLE` و `FORCE` روی DB هدف **فقط پس از** smoke-test همه مسیرها، Backup/restore، تست دو Tenant، بودجه Pool، monitoring و تأیید امنیت مستقل.
5. حذف نقش `SUPERUSER` / `BYPASSRLS` و مالکیت جدول از Runtime، آزمایش کامل جلوگیری از تزریق SQL و cross-tenant query و بررسی کاربردهای مجاز داده عمومی.
6. اجرای آزمایش بار/خطا و failover، برنامه rollback تأییدشده، حفاظت PHI، consent و کاربری واقعی.

**نکته:** مرحله ۱۹ پروژه شامل چندین سرویس آزمونی route/epoch و pre-auth امن در PostgreSQL Clone است، اما این سرویس‌ها هنوز به `app.main` و `get_db` واقعی وصل نشده‌اند. ادغام آن‌ها با همه Endpointهای فعلی پروژه یک کار امنیتی جدا و بسیار مهم است.

## جمع‌بندی

این PR سخت‌سازی دیتابیس و شواهد RLS روی PostgreSQL موقت را ارائه می‌دهد. **نباید بخش ۲۶ را «جداسازی عملیاتی کامل» یا «Production-ready» نامید**؛ فاز پذیرش Runtime و هویت PostgreSQL هر Tenant باید پیش از عرضه تجاری تکمیل شود.
