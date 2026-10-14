# برنامه تست محلی (پس از انتشار در مخزن خصوصی GitHub)

## پیش‌نیازها

- Windows 10/11 + Docker Desktop با WSL2
- Git + PowerShell 7 یا Windows PowerShell
- حدود 8GB RAM آزاد برای تست راحت
- فایل `.env` ساخته‌شده از `.env.example`، با رمزهای قوی و متفاوت

## راه‌اندازی فقط با داده ساختگی

```powershell
Copy-Item .env.example .env
# .env را باز کنید و POSTGRES_PASSWORD و قسمت رمز اتصال DATABASE_URL را یکسان تعیین کنید
# JWT_SECRET و BOOTSTRAP_ADMIN_PASSWORD را نیز با مقادیر تصادفی قوی تنظیم کنید.
docker compose up --build -d
docker compose ps
docker compose exec api python -m app.bootstrap
```

اگر admin قبلاً ایجاد شده باشد bootstrap دوباره اجرا نخواهد شد؛ این رفتار عمدی است.

مدیریت: `http://localhost:3000`؛ API: `http://localhost:8000/docs`.

## تست‌های واحد API

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
```

## ترتیب سناریوهای آزمایشی

1. لاگین مدیر؛ ثبت بیمار **کاملاً ساختگی**.
2. رضایت‌های intake، communication و medical_documents را برای بیمار ساختگی ثبت کنید.
3. یک پرونده ایجاد و از بخش Operations درخواست ویزا/هتل ثبت کنید؛ وضعیت را تا `awaiting_external` تغییر دهید.
4. بدون کد تأیید مستقل، تأیید را تست کنید (باید 422 برگرداند). در تست، مرجع ساختگی با برچسب TEST ثبت کنید.
5. پزشک آزمایشی بسازید، تأیید کنید و درخواست ارجاع به پزشک را امتحان کنید.
6. پیش‌فاکتور به همراه سطرهای هزینه با منبع قیمت آزمایشی ایجاد کنید و تأیید مدیر را تست کنید.
7. لینک دسترسی بیمار را از POST `/api/v1/portal/invites/{patient_id}` دریافت و از مسیر `http://localhost:3000/patient-portal#access=TOKEN` باز کنید (با TOKEN واقعی تست).
8. در پرتال بیمار، پیام ساختگی ارسال کنید و آن را در پنل مکالمات بررسی کنید.
9. بدون تنظیم کلید، تست آپلود فایل باید خطای 503 برگرداند؛ این رفتار امنیتی عمدی است.
10. برای فعال‌سازی مدارک **توسعه‌ای**، متغیرهای `ALLOW_DEV_ENCRYPTED_UPLOADS=true`، `PRIVATE_DOCUMENT_DIR` و `DOCUMENT_ENCRYPTION_KEY` را با کلید ۳۲‌بایتی تصادفی تنظیم کنید. هرگز مدارک واقعی وارد نکنید.

## مواردی که عمداً فعال نمی‌شوند

- اتصال واقعی واتساپ در ایران یا کشورهای دارای محدودیت
- AI خارجی بدون مجوز استفاده و شرایط پردازش داده پزشکی
- پرداخت واقعی، رزرو رسمی، صدور یا تأیید ویزا
- بارگذاری اسناد واقعی پزشکی در مسیر توسعه

این تست محلی به معنی تأیید آمادگی تولید نیست.
