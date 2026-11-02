# بخش ۳۷ — SaaS Subscription / اشتراک‌های سازمانی

## خروجی کد
- جدول `tenant_subscriptions` با حداکثر یک اشتراک به‌ازای هر Tenant، FK مرکب برای عامل اعطا، و RLS policy آماده اما غیر‌فعال در Production.
- `GET /api/v1/saas/plans`: پلن‌های توسعه‌ای starter/professional/enterprise، بدون قیمت یا پرداخت.
- `GET /api/v1/saas/subscription`: فقط مدیر Tenant و بدون مشاهده اشتراک دیگر سازمان‌ها.
- `POST /api/v1/saas/subscription/evaluation`: یک‌بار ایجاد اشتراک آزمایشی داخلی توسط مدیر سازمان با Audit. **بدون تراکنش مالی، ارتقای خودکار، تمدید یا فعال‌سازی پولی.**
- تست مصنوعی: `backend/tests/test_section_37_saas.py` شامل کنترل نقش، Tenant، پلن نامعتبر و تکرار درخواست.
- Migration: `a37e904d12ab_saas_subscription.py` با parent بخش ۲۷. اگر شاخه‌های ۲۸ تا ۳۶ را ادغام کردید باید پیش از ادغام این migration، ترتیب Alembic را با تاریخچه ادغام‌شده تطبیق دهید. اجرای کورکورانه روی دیتابیس مشتری ممنوع است.

## تست
```powershell
git fetch origin
git switch feature/section-37-saas-subscription
docker compose exec api pytest -q tests/test_section_37_saas.py
```
این تست در جلسه فعلی اجرا نشده و هیچ موفقیتی برای CI یا Migration ادعا نمی‌شود.

## کارهای باقی‌مانده تا اجرای کامل پرامپت
1. تعریف پلن در جداول versioned و چرخه trial/active/past_due/suspended/cancelled با transition کنترل‌شده.
2. تعریف quota/entitlements و enforce اتمی آن در همه مسیرهای API، Worker، اسناد، AI و پیام‌ها با فیلتر Tenant.
3. شمارش قابل حسابرسی میزان مصرف و جلوگیری از overage در concurrent requests.
4. صورت‌حساب و فاکتور، مالیات و PSP مجاز، webhooks امضاشده، idempotency، تطبیق پرداخت و refund.
5. ارتقا/تنزل، grace period، توقف ایمن و نگهداری داده مطابق قانون بدون حذف یا قفل‌شدن اطلاعات بالینی حساس.
6. داشبورد اشتراک و مصرف با طراحی فارسی RTL و RBAC.
7. تست‌های PostgreSQL واقعی، race/replay، امنیت RLS، CI، staging و آزمون پذیریش مالی و حقوقی.

## پذیرش
**این تحویل هسته اشتراک آزمایشی است نه سامانه SaaS تجاری کامل.** هیچ اقدام مالی یا استفاده از اطلاعات واقعی بیمار مجاز یا تأیید نشده است.
