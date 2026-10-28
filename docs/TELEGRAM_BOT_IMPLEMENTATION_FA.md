# ربات تلگرام MedTour-AI — نسخه توسعه امن

## وضعیت
کد ربات اطلاعات عمومی پنج‌زبانه را در گفت‌وگوی خصوصی ارائه می‌دهد و به کانال رسمی تماس با اپراتور و دعوت‌نامه اختصاصی پرتال ارجاع می‌دهد. **این سامانه نه پرونده پزشکی می‌سازد، نه پیام پزشکی را ذخیره می‌کند، نه ویزا/درمان/رزرو را تأیید می‌کند.** فعال‌سازی واقعی به حساب BotFather، دامنه HTTPS عمومی، تنظیمات مجاز و آزمون امن وابسته است.

## قابلیت‌های کدنویسی‌شده
- پشتیبانی از fa فارسی، ar عربی، en انگلیسی، ps پشتو و prs دری.
- دستورات `/start`، `/help`، `/privacy`، `/language`، `/lang`، `/services`، `/process`، `/operator`، `/emergency` و `/stop`.
- درخواست زبان با `/language fa` یا `/start ar` و مشابه آن؛ انتخاب زبان در دیتابیس ذخیره نمی‌شود.
- `/operator` صرفاً URL عمومی و از پیش پیکربندی‌شده تماس با نیروی انسانی را معرفی می‌کند. لینک شخصی دعوت‌نامه، شناسه کاربر، داده پزشکی یا پرونده از تلگرام ساخته نمی‌شود.
- پیام‌های آزاد یا فایل‌ها به شکل امن نادیده گرفته می‌شوند؛ فقط پیام هشدار عمومی پاسخ داده می‌شود.
- تأیید Webhook با هدر `X-Telegram-Bot-Api-Secret-Token`، محدودیت سخت‌گیرانه حجم JSON، گفت‌وگوی خصوصی، جلوگیری از بازپخش به کمک Redis، و عدم تکرار ناخواسته ارسال هنگام وضعیت نامشخص.
- محیط مستقل عمومی با `app.telegram_entrypoint:app` فقط یک مسیر `POST /api/v1/webhooks/telegram` دارد؛ هیچ مسیر مدیریت، بیمار، پرونده یا هوش مصنوعی در آن تعریف نشده است.
- سرویس `telegram-gateway` اختیاری در Compose (profile=`telegram`) بدون متغیرهای پایگاه‌داده، روی پورت محلی ۸۰۰۱ و با فایل‌سیستم فقط خواندنی.

## تنظیمات موردنیاز — فقط روی محیط تحت کنترل خودتان
کلیدهای زیر را در فایل `.env` شخصی و خارج از Git نگهداری کنید؛ **مقادیر را در گفتگو ارسال نکنید**:
```dotenv
TELEGRAM_BOT_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
PUBLIC_PRIVACY_NOTICE_URL=
PUBLIC_OPERATOR_CONTACT_URL=
```
`PUBLIC_OPERATOR_CONTACT_URL` اختیاری است. دو URL باید HTTPS عمومی و بدون توکن، query، fragment یا نام کاربری در URL باشند. `TELEGRAM_WEBHOOK_SECRET` باید رشته تصادفی ۳۲ تا ۲۵۶ حرف/عدد/underscore/خط‌تیره باشد. `REDIS_URL` در سرویس Compose مستقل به Redis داخلی تنظیم می‌شود.

## آزمون بدون ارتباط به تلگرام واقعی
تست‌های `backend/tests/test_telegram.py` و `backend/tests/test_section_35_devops.py` با mock provider و Redis اجرا می‌شوند. برای بررسی پیکربندی:
```powershell
docker compose config --format json | python scripts/verify_compose.py
```
برای راه‌اندازی محلی بعد از تنظیم محیط آزمایشی:
```powershell
docker compose --profile telegram up -d --build telegram-gateway
```
این پورت **به‌تنهایی Webhook قابل‌دسترسی تلگرام نیست**. باید Reverse Proxy با HTTPS معتبر و مسیر `/api/v1/webhooks/telegram` آن را به Gateway مستقل متصل کند. مسیر پنل ادمین را در معرض عموم قرار ندهید.

## ثبت Webhook واقعی
پس از داشتن BotFather token و دامنه HTTPS مجاز، از `scripts/configure-telegram-webhook.ps1` استفاده کنید. این اسکریپت فقط خود وبهوک را در Telegram API ثبت می‌کند و نباید نام/محتوا/مدارک بیمار را ارسال کند.

## محدودیت‌ها و پذیرش
- این توسعه به‌تنهایی یعنی «ربات راهنمای امن» نه ربات کامل پردازش بالینی یا CRM تلگرام. اتصال پرونده صرفاً در پرتال با احراز هویت مستقل و رضایت معتبر مجاز است.
- پاسخ‌های چندزبانه نیازمند بازبینی انسانی ترجمه هستند.
- تست GitHub Actions جای آزمون BotFather/HTTPS/Redis واقعی و شرایط ارائه‌دهنده را نمی‌گیرد.
- تست واقعی شبکه در مرحله بعد و فقط با داده مصنوعی و راهبری کارفرما انجام می‌شود.


## اجرای مداوم محلی با Polling — فقط محیط توسعه و یک گفت‌وگوی مجاز

یک سرویس مستقل `telegram-poller` در profile `telegram-polling` وجود دارد. این سرویس:
- نیازمند `APP_ENV=development`، `TELEGRAM_POLLING_ENABLED=true` و `TELEGRAM_POLLING_TEST_MODE=true` است.
- فقط به شناسه یک گفت‌وگوی خصوصی که با چالش تصادفی تأیید شده پاسخ می‌دهد؛ پیام‌های سایر کاربران را پاسخ نمی‌دهد.
- برای پیام‌های عادی مانند «سلام» **فقط هشدار عمومی امن** می‌فرستد؛ ChatGPT، تشخیص، پرونده، رزرو یا سامانه پزشکی به آن وصل نیست.
- به PostgreSQL یا اعتبارنامه‌های هسته دسترسی ندارد و هیچ پورتی روی میزبان باز نمی‌کند.
- از Redis برای حفظ offset، جلوگیری از تکرار پیام و قفل یک دریافت‌کننده استفاده می‌کند.
- بدون URL سیاست حریم خصوصی معتبر، فقط در حالت **development/test** پیام هشدار درون‌ساخت ارسال می‌کند و **هیچ URL ساختگی** اضافه نمی‌کند.

۱. داخل ویندوز با **PowerShell** و بدون ارسال توکن در گفتگو، اسکریپت زیر را اجرا کنید:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Downloads\MedTour-AI-Integrated-1-to-45\scripts\setup-telegram-local-polling.ps1"
```

۲. اسکریپت BotFather Token را به‌صورت مخفی می‌گیرد و فقط پس از دریافت یک چالش جدید در گفت‌وگوی خصوصی، شناسه همان گفت‌وگو را در فایل `.env` محلی و خارج از Git ثبت می‌کند. **این کار توکن را به شکل متن در فایل `.env` و متغیرهای محیط Docker ذخیره می‌کند**؛ برای استفاده تجاری باید ابتدا توکن افشاشده را در BotFather تعویض کنید و مدیریت اسرار استقرار را تکمیل کنید.

۳. اجرای سرویس مستقل:

```powershell
docker compose --profile telegram-polling up -d --build telegram-poller
```

۴. مشاهده وضعیت بدون نمایش توکن:

```powershell
docker compose --profile telegram-polling ps telegram-poller
```

۵. توقف:

```powershell
docker compose --profile telegram-polling stop telegram-poller
```

مهم: `getUpdates` و Webhook روی یک ربات نباید هم‌زمان فعال شوند؛ اگر Webhook موجود باشد، Poller شروع نمی‌شود. بیش از یک دریافت‌کننده Polling اجرا نکنید. به‌روزرسانی‌ها و پیام‌ها را برای استفاده عمومی باز نکنید. این قابلیت فقط راهنمای آزمایشی است و به معنی آمادگی تولید بالینی یا راه‌اندازی پایدار عمومی نیست.
