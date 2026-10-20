# مرحله ۱۹.۱۶ — آزمون FastAPI روی PostgreSQL با RLS (ایزوله)

**وضعیت:** اسکریپت‌ها و داده‌های ساختگی در GitHub ثبت شده‌اند. نتیجه موفق اجرای Docker هنوز دریافت نشده است.

## نتایج قبلی (تأییدشده)

- ۱۹.۱۳: RLS مبتنی بر `session_user` در PostgreSQL Clone موفق شد.
- ۱۹.۱۴: SQLAlchemy Pool مجزا برای هر Tenant موفق شد.
- ۱۹.۱۵: شش تست جدید و کل مجموعه Backend (`54 passed, 1 warning`) در SQLite آفلاین موفق شدند. هشدار مربوط به deprecation ابزار `starlette.testclient` است، نه شکست تست.

## دامنه مرحله ۱۹.۱۶

اجرای `scripts/rls-fastapi-endpoint-clone-test.ps1` یک شبکه `docker network --internal` و دیتابیس PostgreSQL 17 تازه می‌سازد؛ Backup ساختگی را بازگردانی و Policyهای مرحله ۱۹.۱۳ را روی هر ۳۷ جدول اعمال می‌کند؛ کاربران و توکن‌های ساختگی را به همان Clone اضافه می‌کند؛ و TestClient خودِ `app.main` را با `get_db` آزمایشی به دو Pool واقعی `mt_clone_a` و `mt_clone_b` وصل می‌کند.

پوشش: JWT معتبر/بیگانه، خواندن و ثبت بیمار، IDOR، محدودسازی نقش Auditor، Portal Access Token، Consent Preview Token و Refresh Token Rotation/Replay در هر Tenant.

### محدودیت جدی

این یک آزمون end-to-end **برای Endpointهای انتخاب‌شده پس از تزریق اتصال صحیح** است؛ پیاده‌سازی سازوکار عملیاتی انتخاب Pool امن نیست. خود `backend/app/database.py` و Dependency `get_db` تغییر نکرده‌اند. Login، Webhook WhatsApp، Health/Ready، Token Resolver و مسیر پیش از احراز هویت باید جداگانه با Registry کم‌اختیار یا معماری مناسب نهایی شوند. دسترسی HTTP عملیاتی نباید از SUPERUSER یا یک DSN مشترک مدیریتی استفاده کند.

**تغییرات این مرحله روی دیتابیس اصلی، Volumeها، Docker Compose یا تنظیمات Secretهای عملیاتی اعمال نمی‌شود.**

## دستور اجرای Windows PowerShell

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\rls-fastapi-endpoint-clone-test.ps1
```

پیام نهایی مورد انتظار پس از تمام آزمون‌ها:

```
PASS: STAGE 19.16 ISOLATED FASTAPI POSTGRESQL RLS ENDPOINT TEST COMPLETED
```

## گام‌های بعدی

۱. طراحی Resolver مستقل با کمترین مجوز برای Tenant `slug` و هش Refresh/Portal/Consent، مقاوم در برابر جعل و Replay.

۲. تضمین اینکه ابتدا امضای JWT، Webhook Meta یا اعتبار توکن بررسی می‌شود، سپس نقش DB مربوطه انتخاب می‌شود.

۳. جداکردن Alembic و عملیات مدیریتی از Process اجرایی HTTP و استفاده از Secret Manager برای Credentials نقش‌های Tenant.

۴. تست‌های PostgreSQL واقعی برای Login، Health، Webhook، Refresh/Portal/Consent با Tenantهای متعدد، مدیریت Poolها و Fail-closed.

۵. Migration نهایی کلیدهای مرکب و RLS روی Clone + Rollback + بازیابی پیش از هرگونه اعمال روی داده‌های اصلی.
