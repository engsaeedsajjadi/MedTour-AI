# MedTour-AI — شروع مهاجرت عملیاتی (Pilot ایزوله)

**تاریخ:** ۲۱ اکتبر ۲۰۲۶  
**دامنه:** اتصال آزمایشی قابلیت‌های موفق ۱۹.۲۱–۱۹.۲۳؛ این یک مرحله شماره‌دار جدید از آزمون‌های توافق‌شده نیست.

## هدف

گزارش `docs/FINAL_ACCEPTANCE_TEST_REPORT_2026_10_20_FA.md` تأیید کرده که آزمایش‌های امنیتی Clone PASS هستند، اما `main.py`، `security.py`، `session_api.py` و `whatsapp.py` هنوز از مسیر عملیاتی قبلی استفاده می‌کنند. اولین اقدام ایمن، اتصال **Preauth → Epoch Control Plane → Tenant Pool Lease → PostgreSQL RLS** در یک FastAPI جداگانه و بدون پردازش اطلاعات پزشکی است.

## کدهای ایجادشده

- `backend/app/staged_epoch_preauth_bridge.py`:
  - `EpochGuardedSessionFactory` جایگزین استفاده مستقیم از `sessionmaker` در سرویس‌های آزمایشی Preauth است. هر `with factory()` یک بررسی جدید `generation/enabled` از Control Plane مرکزی انجام می‌دهد و فقط در صورت تأیید، Lease و Session از PostgreSQL LOGIN کم‌اختیار می‌گیرد.
  - `create_clone_preauth_pilot()` فقط با `APP_ENV=test` و `DATABASE_URL=sqlite://` و `MEDTOUR_SYNTHETIC_CLONE=1` ساخته می‌شود.
  - تنها سه Endpoint را Mount می‌کند: `POST /api/v1/auth/login`، `POST /api/v1/auth/refresh` و `POST /api/v1/webhooks/whatsapp` (اعتبارسنجی امضا و حساب بدون پردازش پیام).
  - هیچ مسیر بیمار، کیس، مدارک، هوش مصنوعی، پنل مدیریت، پردازش واقعی WhatsApp، مشاهده اطلاعات پزشکی یا دریافت داده خارجی Mount نمی‌شود.
- `backend/app/staged_preauth_service.py` و `backend/app/staged_tenant_transactions.py`: وقتی Epoch رد/Control Plane قطع شود، خطای `LookupError` در سرویس مرحله‌ای به رد امن Login/Refresh/Webhook تبدیل می‌شود؛ استثنای SQLAlchemy همچنان Fail-Closed است.
- `backend/tests/test_pilot_epoch_preauth_bridge.py`: تست Unit برای ثبت Routeهای محدود، جلوگیری از Mount در Production، خواندن Epoch برای هر Session، رد درخواست هنگام قطع/ابطال Control Plane و جلوگیری از fallback.
- `scripts/rls-staged-epoch-pilot-probe.py`: دو Registry مستقل با PostgreSQL Clone مشترک، ورود و Refresh واقعی دو Tenant از طریق FastAPI TestClient، اعتبارسنجی امضای Meta بدون ذخیره PHI، ابطال A و باقی‌ماندن B، سپس فعال‌سازی A در Epoch بعدی.
- `scripts/rls-staged-epoch-pilot-clone-test.ps1`: Runner با Docker شبکه داخلی و Restore فقط Backup ساختگی. `main.py` و Docker Compose را تغییر نمی‌دهد.

## اجرای تست‌های Pilot

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main

# فقط تست Unit آفلاین، بدون PostgreSQL و Network
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -PilotOnly

# فقط با Backup ساختگی و بدون پرونده بیمار واقعی:
& .\scripts\rls-staged-epoch-pilot-clone-test.ps1
```

**پیام‌های مورد انتظار (تا زمان اجرا در محیط کاربر تأیید نشده):**

```text
PASS: RUNTIME MIGRATION PILOT EPOCH PREAUTH FAIL-CLOSED UNIT TESTS COMPLETED
PASS: STAGED RUNTIME MIGRATION PILOT ISOLATED EPOCH PREAUTH FASTAPI TEST COMPLETED
```

اگر تست خطا داد، مستقیماً Debug و اصلاح می‌شود؛ **هیچ Migration یا Deploy خودکاری پس از PASS اجرا نمی‌شود**.

## موارد مسدودکننده برای مهاجرت واقعی

1. **عدم دست‌زدن به سرویس جاری:** `backend/app/main.py`، `backend/app/database.py`، `backend/app/security.py`، `backend/app/session_api.py`، `backend/app/whatsapp.py`، `backend/alembic`، `docker-compose.yml` و `.env` در این Pilot تغییر نمی‌کنند.
2. **مهاجرت توکن‌های قدیمی:** توکن‌های قدیمی Plain بدون اطلاعات مسیر Tenant نباید ناگهان ناپدید یا قابل جعل شوند؛ نیاز به Cutover Plan و سیاست لغو یا خروج اجباری Session وجود دارد.
3. **مرز اجرای فعلی:** Route محافظت‌شده `current_user` هنوز از `get_db` مشترک استفاده می‌کند. لازم است تمام Routeها به‌صورت آگاه از Tenant و با نقش DB محدود منتقل شوند؛ انجام این تغییر با جایگزینی یک Dependency عمومی بدون بررسی ممکن نیست.
4. **RLS/DDL:** جدول‌ها و Policyهای آزمایش‌شده روی Clone باید در Migrationهای واقعی با Backup، قفل، Rollback Plan، کنترل اختیارات و برنامه Downtime بررسی شوند. اجرای خودکار DDL روی Production ممنوع است.
5. **Meta/PHI:** تنها اعتبارسنجی Signed Webhook آزمایش می‌شود؛ این Pilot پیام را ذخیره، بیمار را شناسایی، Consent را تغییر یا پاسخی ارسال نمی‌کند.
6. **چند Worker واقعی:** Registryها در یک Process تست می‌شوند. Load/Failover/Multi-Process و TLS هنوز اثبات نشده‌اند.
7. **Secret/Key rotation و حفاظت اطلاعات:** Secret Manager، کلیدهای HMAC/JWT، حساب WhatsApp، الزامات قراردادی و حریم خصوصی، Audit، Monitoring و Backup Restore باید جداگانه آماده شوند.
8. **امنیت عملیات:** ساخت Provisioned Registry و Role mapping باید از منبع Provisioning مورداعتماد باشد، نه ورودی HTTP. کلیدهای تست در مخزن قابل انتشار نباید در Production استفاده شوند.

**نتیجه قابل ادعا بعد از PASS:** فقط «Preauth مرحله‌ای با Epoch Guard و RLS در FastAPI جداگانه روی Clone موفق بوده است». این نتیجه مجوز ورود به Production یا استفاده از PHI واقعی نیست.
