# MedTour-AI — مسیر عملیاتی اولین تست تلگرام (MVP کانال عمومی)

**۲۱ اکتبر ۲۰۲۶ — توسعه مرحله‌ای در شاخه main.** این قابلیت تکمیل بخش «کانال واقعی» پرامپت اصلی نیست؛ یک اتصال حداقلی امن برای اولین تعامل با ربات رسمی تلگرام است.

## چه چیزی اضافه شد؟

- `backend/app/telegram.py`: دریافت آپدیت رسمی Telegram Bot API با `X-Telegram-Bot-Api-Secret-Token`، احراز secret با `compare_digest`، سقف payload برابر ۶۴ کیلوبایت، فقط چت خصوصی، پیام‌های عمومی پنج‌زبانه، پاسخ فقط بعد از پیام ورودی کاربر، جلوگیری از پردازش تکراری با Redis و رد ایمن در قطع Redis/Telegram.
- `backend/app/telegram_entrypoint.py`: **اپلیکیشن مستقل فقط یک Route** برای قرارگیری پشت Reverse Proxy با HTTPS. نباید `app.main` یا پورت مدیریتی بیمار را فقط برای دریافت Webhook در اینترنت باز کرد.
- `backend/app/main.py`: Route اضافه شده ولی `TELEGRAM_BOT_ENABLED=false` به‌طور پیش‌فرض هرگونه پردازش را مسدود می‌کند. وضعیت پیکربندی از API integrations/status معلوم است، نه وضعیت اتصال واقعی.
- `backend/tests/test_telegram.py`: ۱۹ سناریوی آفلاین احراز اصالت، تکرار، ورودی ناسالم، زبان‌ها و حفظ حریم خصوصی.
- `scripts/test-stage-19-15-auth-boundaries.ps1 -TelegramOnly`: اجرای تست‌های Telegram در کانتینر بدون شبکه روی فایل‌های فعلی پروژه.
- `scripts/configure-telegram-webhook.ps1`: ابزار امن برای تنظیم `setWebhook` رسمی با `allowed_updates=["message"]`، بدون چاپ Token.

## مراحل تست بدون حساب Meta

۱. در تلگرام رسمی با <https://t.me/BotFather> ربات مخصوص کسب‌وکارتان را از طریق `/newbot` بسازید. Bot Token را محرمانه نگه دارید.

۲. ابتدا تغییرات مخزن و تست آفلاین را اجرا کنید:

```powershell
cd "D:\Downloads\MedTour-AI-Enterprise-v0.5.0-alpha\MedTour-AI"
git pull --ff-only origin main
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -TelegramOnly
# و سپس برای جلوگیری از Regression:
& .\scripts\test-stage-19-15-auth-boundaries.ps1 -FullSuite
```

۳. برای تست اینترنتی، دامنه **HTTPS عمومی با گواهی معتبر**، Redis مستقل و راه‌اندازی تنها `uvicorn app.telegram_entrypoint:app` لازم است. از اتصال مستقیم `main.py` به اینترنت و از بارگذاری اطلاعات واقعی بیمار اجتناب کنید.

۴. Secrets را **فقط روی سرور/محیط امن** (نه در GitHub یا گفتگو) تنظیم کنید:

```dotenv
TELEGRAM_BOT_ENABLED=true
TELEGRAM_BOT_TOKEN=<REPLACE_WITH_PRIVATE_BOTFATHER_TOKEN>
TELEGRAM_WEBHOOK_SECRET=<REPLACE_WITH_RANDOM_32_TO_256_ALPHANUMERIC_SECRET>
PUBLIC_PRIVACY_NOTICE_URL=https://example.org/privacy
REDIS_URL=rediss://<YOUR_SECURE_REDIS_SERVER>
```

۵. پس از آماده بودن Endpoint عمومی HTTPS، همین Secrets را در Session امن PowerShell قرار دهید و Script ثبت Webhook را اجرا کنید:

```powershell
& .\scripts\configure-telegram-webhook.ps1 -PublicBaseUrl "https://your-verified-domain.example"
```

آزمایش با `/start fa`، `/language ar`، `/language en`، `/language ps` و `/language prs` انجام می‌شود. فقط متن راهنما و لینک سیاست حریم خصوصی برمی‌گردد. هیچ تشخیص، قیمت، نوبت واقعی، پرونده پزشکی یا Consent از تلگرام صادر نمی‌شود.

### مرزهای پذیرفته‌نشده برای Production

- تعامل Telegram در این نسخه فقط پیام عمومی و دعوت به پرتال امن است. **پیام پزشکی و مدارک خصوصی ذخیره یا به AI منتقل نمی‌شوند.**
- Telegram Bot API به‌تنهایی احراز هویت بیمار در MedTour-AI نیست؛ حساب Telegram معادل User/Patient معتبر SaaS نیست.
- Bot Token فعلاً **تک‌ربات/تک‌استقرار** است. برای SaaS چندسازمانی باید Bot→Tenant mapping مورداعتماد، Tenant Pool/RLS Runtime، Secret Manager و Revocation عملیاتی تکمیل شوند.
- ارسال مستقیم HTTP در Webhook فقط برای متن عمومی MVP است. قبل از بار عملیاتی، Worker/Outbox قابل بازیابی و Retry پس از قطع ارتباط لازم است.
- احراز هویت بیماران، تکمیل Consent، CRM واقعی، پردازش PHI، انسان در حلقه تصمیم پزشکی، مستندات قرارداد/محدودیت کشورها و Portal Security هنوز در دست تکمیل هستند.
- تست آفلاین و موفقیت GitHub CI به‌معنی آزمایش واقعی Telegram یا آماده‌بودن محصول Enterprise نیست.
- دقت ترجمه پنج زبان نیازمند بازبینی بومی‌زبان است.

## نتیجه قابل ادعا

**Telegram public onboarding gateway — code delivered, offline tests pass; external webhook/account and end-to-end patient journey not yet certified.** هدف بعدی پس از تأیید کانال: طراحی ورود بیمار با رضایت آگاهانه در پرتال، تخصیص Tenant معتبر و اتصال کارتابل اپراتور به‌صورت فاقد انتشار اطلاعات پزشکی در پیام‌رسان.
