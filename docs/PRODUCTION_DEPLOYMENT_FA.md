# استقرار نهایی MedTour-AI (production)

این راهنما سیستم را روی یک سرور با دامنه اختصاصی و HTTPS بالا می‌آورد. اگر هنوز دامنه ندارید، همین مراحل را با `PUBLIC_DOMAIN=localhost` و `APP_ENV=staging` روی سیستم خودتان اجرا کنید.

## معماری

فقط Caddy روی پورت‌های 80 و 443 از بیرون در دسترس است. Caddy گواهی HTTPS را خودکار می‌گیرد و درخواست‌ها را این‌طور پخش می‌کند:

| مسیر | سرویس |
| --- | --- |
| `/api/v1/webhooks/telegram` | `telegram-gateway` (بدون دسترسی به پایگاه داده) |
| `/api/*` | `api` (نقش غیرممتاز `medtour_app` با RLS اجباری) |
| بقیه | `web` (پنل فارسی) |
| `/docs`، `/openapi.json` | مسدود (404) |

پایگاه داده، Redis، MinIO، ClamAV و API هیچ پورت عمومی ندارند. سرویس `backup` هر ۲۴ ساعت پایگاه داده و مدارک را رمزنگاری‌شده پشتیبان می‌گیرد.

## ۱. آماده‌سازی سرور

- لینوکس با Docker و Docker Compose نسخه 2.24 یا بالاتر
- رکورد DNS نوع A برای دامنه (مثلاً `panel.example.com`) به IP سرور
- پورت‌های 80 و 443 باز؛ همه پورت‌های دیگر بسته

## ۲. تنظیمات

```bash
git clone -b integration/medtour-45-unified-candidate https://github.com/engsaeedsajjadi/MedTour-AI.git
cd MedTour-AI
cp .env.production.example .env
chmod 600 .env
```

همه مقادیر خالی `.env` را پر کنید. دستور ساخت کلیدها و رمزها در بالای همان فایل آمده است. `BACKUP_PASSPHRASE` را در یک مدیر رمز **بیرون از سرور** نگه دارید؛ بدون آن هیچ پشتیبانی قابل بازیابی نیست.

## ۳. اجرا

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile secure-storage up -d --build
```

ربات تلگرام هم اگر فعال است: `--profile telegram` را به همین دستور اضافه کنید.

## ۴. ساخت سازمان و مدیر اول

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate \
  python -m app.provision_tenant --slug clinic-a --name "نام سازمان" --admin-email admin@clinic-a.example
```

رمز بدون نمایش پرسیده می‌شود (حداقل ۱۴ نویسه). مدیر در اولین ورود باید ورود دومرحله‌ای را از صفحه «امنیت حساب» فعال کند. برای هر مشتری جدید همین دستور را با `slug` جدید اجرا کنید.

## ۵. ربات تلگرام

1. در `.env`: `TELEGRAM_BOT_ENABLED=true`، `TELEGRAM_BOT_TOKEN` (از BotFather)، `TELEGRAM_WEBHOOK_SECRET` و `PUBLIC_OPERATOR_CONTACT_URL`.
2. سرویس را با `--profile telegram` بالا بیاورید.
3. ثبت webhook (ویندوز): `scripts/configure-telegram-webhook.ps1 -PublicBaseUrl https://panel.example.com`
4. در تلگرام `/start` بفرستید و پاسخ پنج‌زبانه را بررسی کنید.

حالت polling (`telegram-poller`) فقط برای تست توسعه است و در production اجرا نمی‌شود.

## ۶. بررسی پس از استقرار

```bash
# فقط medtour_app به API وصل است و ۸۸ جدول RLS اجباری دارند
docker compose exec -T db psql -U medtour -d medtour -c "select usename,count(*) from pg_stat_activity where datname='medtour' group by 1;" \
  -c "select count(*) filter (where relrowsecurity) rls_on, count(*) filter (where relforcerowsecurity) rls_forced from pg_class where relkind='r' and relnamespace='public'::regnamespace;"

# تمرین بازیابی پشتیبان (پایگاه داده اصلی دست‌نخورده می‌ماند)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup backup.sh --once
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup verify-restore.sh
```

در پنل، صفحه «ممیزی جداسازی سازمان‌ها» وضعیت همه کنترل‌ها را نشان می‌دهد.

## ۷. دروازه انتشار برای بیمار واقعی

با `APP_ENV=production`، API فقط وقتی اجرا می‌شود که هر دو شرط زیر برقرار باشد:

1. **همه کنترل‌ها در `/api/v1/compliance/readiness` کامل باشند:** RLS، MFA، ارسال کد بیمار، مخزن امن با اسکن بدافزار، دوره نگهداری، Redis، اطلاعیه حریم خصوصی و مراجع حقوقی.
2. **فایل `backend/release/PRODUCTION_APPROVAL.json` در مخزن ثبت شده باشد** و مرجع این بازبینی‌های مستقل را داشته باشد:
   - تست نفوذ مستقل
   - بازبینی ایمنی بالینی
   - ارزیابی اثر بر حریم خصوصی (DPIA) برای کشورهای هدف
   - تمرین بازیابی پشتیبان روی همین سرور
   - قراردادهای ارائه‌دهندگان
   - نام دست‌کم دو تأییدکننده

   ساختار فایل در `backend/app/release_approval.py` آمده است. این فایل فقط از طریق Pull Request بازبینی‌شده و **پس از انجام واقعی** این بازبینی‌ها اضافه می‌شود. هیچ متغیر محیطی نمی‌تواند جایگزین آن شود.

تا آن زمان سیستم را با `APP_ENV=staging` و فقط با داده ساختگی اجرا کنید.
