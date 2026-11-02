# بخش ۳۵ — DevOps و آماده‌سازی استقرار

## وضعیت
فقط زیرساخت Development و کنترل‌های پیش‌استقرار تقویت شده‌اند. **هیچ استقرار Production، ارزیابی امنیت یا تأیید استفاده از داده بیمار واقعی انجام نشده است**.

## تغییرات
- `docker-compose.yml`: مهاجرت Alembic از command اجرای API خارج و به سرویس یک‌بار‌اجرای `migrate` منتقل شد.
- `api` و `outbound-worker` در صورت اجرای پروفایل messaging باید منتظر `service_completed_successfully` مهاجرت باشند.
- `scripts/verify_compose.py`: گزارش خطا برای سرویس ناقص، انتشار host port بدون loopback، worker بدون پروفایل opt-in و migration همزمان با راه‌اندازی API.
- `.github/workflows/compose-preflight.yml`: بررسی Compose روی CI با فایل محیطی مصنوعی موقت.
- `backend/tests/test_section_35_devops.py`: واحدهای کنترل روی سیاست‌های محیط توسعه.

## تست محلی — بدون بیماران واقعی
```powershell
git fetch origin
git switch feature/section-35-devops-preflight
docker compose config --format json | python scripts/verify_compose.py
cd backend
python -m pytest -q tests/test_section_35_devops.py
cd ..
docker compose up -d --build
docker compose ps
```
تست‌ها در این گفتگو هنوز اجرا نشده‌اند. اجرای Compose از روی پروژه واقعی ممکن است از Volume موجود استفاده کند؛ پیش از هر Migration از DB نسخه پشتیبان معتبر تهیه کنید.

## ریسک‌های باقی‌مانده برای Production
1. مهاجرت Alembic فعلاً در هر `docker compose up` یک‌بار اجرا می‌شود؛ استقرار چند replica به release job/lease مستقل و rollout کنترل‌شده نیاز دارد.
2. image pinning با digest، SBOM، SAST/SCA و اسکن container، تأیید provenance و supply-chain security لازم است.
3. SSL/TLS termination، WAF، شبکه خصوصی service-to-service، secrets manager و دسترسی حداقلی موردنیازند.
4. Backup + PITR رمزنگاری‌شده و تست بازیابی مستقل با RPO/RTO تصویب‌شده و monitoring/alerting باید فعال شوند.
5. تست‌های بار، chaos، rollback و blue-green/canary با محیط staging ضروری‌اند.
6. RLS واقعی، چرخش roleهای Tenant، KMS/S3/ClamAV و ارزیابی پزشکی/حقوقی/امنیتی قبل از پذیرش اطلاعات واقعی بیماران باقی مانده‌اند.
7. اجرای `APP_ENV=production` همچنان توسط Gateهای Alpha عمداً محدود است.

**پذیرش بخش ۳۵:** اجرای CI، آزمایش migration upgrade و rollback روی clone، بازبینی logs، آزمون Docker staging و تأیید عملیات و امنیت توسط مسئول مجاز.
