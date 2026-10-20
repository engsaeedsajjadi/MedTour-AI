# مرحله ۱۹.۱۵ — مسیر‌یابی معتبر Tenant پیش از اتصال پایگاه‌داده

**دامنه:** طرح امنیتی و تست رگرسیون. این سند یا آزمون‌ها اتصال فعلی API، نقش PostgreSQL زنده یا RLS عملیاتی را تغییر نمی‌دهند.

## خروجی مراحل قبلی

- ۱۹.۱۱: هر ۴۸ Foreign Key مرکب آزمایشی روی Clone اعتبارسنجی شد؛ نه روی دیتابیس عملیاتی.
- ۱۹.۱۲: دسترسی نقش اجرایی بدون مجوز مدیریتی و RLS روی Clone بررسی شد؛ متغیر `medtour.tenant_id` قابل جعل بود.
- ۱۹.۱۳: دو نقش LOGIN و RLS بر پایه `session_user` روی Clone با PASS نهایی آزمایش شد.
- ۱۹.۱۴: Connection Pool جدا برای هر نقش با ORM و هم‌زمانی روی Clone با PASS نهایی آزمایش شد.
- **۱۹.۱۵:** مسیرهای شناسایی Tenant در FastAPI باید قبل از هرگونه تغییر در اتصال عملیاتی ممیزی و بازطراحی شوند.

## یافته‌های مبتنی بر کد فعلی

| مسیر | روش فعلی تشخیص کاربر/Tenant | مانع مهاجرت مستقیم به Poolهای نقش‌محور |
| --- | --- | --- |
| `/api/v1/auth/login` | جست‌وجوی سراسری `Tenant.slug`، سپس کاربر متعلق به Tenant و بررسی رمز | اسلاگ ورودی غیرمعتبر است؛ ابتدا باید Tenant از Registry بسیار محدود یافت و سپس Credential در DB همان Tenant بررسی شود |
| `/api/v1/auth/refresh` | جست‌وجوی سراسری `RefreshSession.refresh_hash` همراه قفل ردیف | توکن بدون Tenant Hint می‌آید؛ Resolver امن باید Tenant توکن را تشخیص دهد و Refresh/Replay در Pool آن Tenant اتمیک انجام شود |
| `/api/v1/portal/me` و Journey/Chat | هش `X-Patient-Access` در جدول `PortalAccess` جست‌وجو می‌شود | Resolver توکن با کمترین دسترسی لازم است؛ فقط پس از Resolve و کنترل انقضا/لغو، Pool مناسب قابل استفاده است |
| `/api/v1/consent-links/preview` و `/respond` | جست‌وجوی سراسری `PatientConsentChallenge.token_hash` | نیازمند Resolve توکن و تراکنش اتمیک یک‌بارمصرف در Pool همان Tenant؛ توکن به‌صورت Query در preview از نظر نشت در لاگ/History نیز باید بازبینی شود |
| `/api/v1/webhooks/whatsapp` | بررسی امضای خام Meta، سپس `WHATSAPP_TENANT_SLUG` و `Tenant.slug` | اتصال Tenant باید پس از احراز صحت امضا و تطبیق شماره/حساب مجاز، از نگاشت قابل‌اعتماد سروری انتخاب شود؛ نه ورودی درخواست |
| `current_user` (JWT staff) | JWT شامل `tid` و `sub`؛ سپس Query به `User` و `RevokedAccess` | اعتبارسنجی رمزنگاری JWT باید قبل از تخصیص Pool انجام شود؛ عضویت فعال و Revocation از DB همان Tenant کنترل شوند |
| `/api/v1/health/ready` | `SELECT count(*) FROM tenants` با `get_db` مشترک | نقش اجرایی جدید به جدول مدیریتی `tenants` دسترسی ندارد؛ Health Check باید با نقش محدود و بدون دسترسی Registry قابل اجرا باشد |

## اصول الزامی برای طراحی نهایی

1. **هر Tenant یک Login/Engine/Pool مستقل:** هر `Engine` فقط برای نقش احرازشده همان Tenant ایجاد شود. از `SET ROLE` یا متغیر Session برای تعویض Tenant استفاده نشود.
2. **Resolver با حداقل دسترسی:** جست‌وجوی هش Refresh/Portal/Consent و Registry عمومی باید از APIهای مشخص با حداقل داده خروجی انجام شود، نه یک Connection مدیریتی آزاد یا Superuser مشترک.
3. **Source of truth سروری:** شناسه Tenant ارسالی از Header/Query/Body مجوز دسترسی محسوب نشود. JWT امضاشده، توکن پرانتروپی معتبر یا Webhook امضاشده شرط لازم Resolve هستند، ولی کنترل کاربر/رضایت/انقضا/لغو در دیتابیس مربوطه همچنان لازم است.
4. **محدودسازی Poolها:** مجموعه Engineهای هر Tenant باید سقف Connection، ظرفیت و زمان‌بندی دفع Pool داشته باشد؛ در غیر این صورت رشد Tenantها می‌تواند اتصال‌های PostgreSQL را اشباع کند.
5. **چرخش و لغو Credentials:** رمزهای DB از Secret Manager دریافت و چرخانده شوند؛ پس از حذف Tenant، Engine و اتصال‌های آن بسته شود؛ هرگونه Cache کلیدها با عمر کوتاه و قطع دسترسی در زمان Revocation مدیریت شود.
6. **Bootstrap و Migrations جدا:** API فعلی با `medtour` دارای SUPERUSER و `BYPASSRLS` اجرا می‌شود؛ اجرای Alembic در Startup API باید پیش از مهاجرت جدا شود و نقش مهاجرت هرگز در اختیار Process پاسخ‌گوی HTTP نباشد.
7. **Atomicity و شکست امن:** Token Resolver و تغییر وضعیت توکن نباید موجب Race یا Cross-Tenant شود؛ خطا در Resolve/Pool/DB باید دسترسی را رد کند، نه به Pool پیش‌فرض با سطح بالاتر برگردد.
8. **داده پزشکی:** قبل از هر استقرار واقعی، کنترل دسترسی اسناد، لاگ‌های حساس، رضایت‌نامه، چرخه حذف اطلاعات و ارزیابی امنیت/حریم خصوصی مستقل لازم است.

## تست‌های این مرحله

فایل `backend/tests/test_stage_19_15_tenant_auth_boundaries.py` شش آزمون با داده ساختگی و SQLite TestClient دارد:

- JWT معتبر با Tenant ID نادرست رد می‌شود.
- Login نمی‌تواند ایمیل Tenant دیگری را احراز هویت کند.
- Replay شدن Refresh در A، Refresh معتبر B را باطل نمی‌کند.
- لینک Portal به Patient و Tenant خود محدود است و پس از Revoke کار نمی‌کند.
- Consent Link بین Tenantها صادر نمی‌شود و Replay آن رد می‌شود.
- Webhook امضاشده متعلق به A، بیمار Tenant B را به A هدایت نمی‌کند.

**توجه:** حتی موفقیت همه این تست‌ها فقط محافظت سطح برنامه در حالت فعلی را نشان می‌دهد. تست مسیر‌یابی واقعی FastAPI با Poolهای PostgreSQL پس از پیاده‌سازی Resolver و Migration جدید باید جداگانه اجرا شود.

## شرایط خروج از مرحله یکپارچه‌سازی

- Login, Refresh, Logout, staff JWT, Portal, Consent و WhatsApp با Tenant Role واقعی در PostgreSQL ایزوله به‌صورت انتهابه‌انتها آزمایش شوند.
- تست‌های منفی JWT/توکن جعلی، Replay، انقضا، تغییر Tenant، درخواست هم‌زمان، توقف Resolver و تعویض رمز DB پوشش داده شوند.
- هیچ Request Handler امکان اتصال به Superuser یا جابه‌جایی بین Tenantها با SQL اختیاری نداشته باشد.
- Migration ترکیبی Foreign Key و RLS همراه Backup، Rollback و تست داده روی Clone معتبر پیش از استقرار اجرا شود.

**تا تحقق این شرایط، فعال‌سازی RLS روی دیتابیس اصلی و تعویض Credential عملیاتی ممنوع است.**
