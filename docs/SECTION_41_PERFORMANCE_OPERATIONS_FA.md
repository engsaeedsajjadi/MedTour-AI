# بخش ۴۱ — Performance & Operations

## وضعیت واقعی
بخش اول پایش صف پیام‌های خروجی پیاده‌سازی شده است. **هیچ تست بار اجرا، هیچ SLO اندازه‌گیری یا تأیید Production انجام نشده است.**

### خروجی‌ها
- `GET /api/v1/operations-metrics/outbox` صرفاً برای admin دارای Tenant معتبر.
- شمارش پیام‌های OutboundMessage براساس وضعیت، شامل approved/sent/delivered/needs_reconciliation.
- شمارش پیام‌های approved قدیمی‌تر از ۱۵ دقیقه (از created_at). این مقدار **تقریب سن صف** است و الزاماً زمان تأخیر واقعی تأیید انسانی را نشان نمی‌دهد.
- عدم افشای شناسه بیمار، متن پیام یا credentials و محدودشدن همه queryها به Tenant.
- تست مصنوعی `backend/tests/test_section_41_operations.py` برای محدودیت نقش، جداسازی Tenant و شمارش عقب‌ماندگی.

### تست پیشنهادی
```powershell
git fetch origin
git switch feature/section-41-performance-operations
cd backend
python -m pytest -q tests/test_section_41_operations.py
```
تست‌ها در این جلسه هنوز اجرا نشده‌اند. تست باید در محیط مصنوعی/ایزوله اجرا شود.

### کارهای لازم برای تکمیل کامل بخش ۴۱
1. تعریف SLI/SLO واقعی برای latency API، نرخ خطا، زمان انتظار اپراتور، صف Worker و تحویل provider.
2. Benchmark با ابزارهایی مانند k6/Locust فقط با داده تست و نرخ مجاز، گزارش p50/p95/p99 و Throughput و Capacity.
3. OpenTelemetry با حذف داده حساس، Prometheus/Grafana، ساخت داشبوردها و قوانین هشدار.
4. وضعیت سلامت واقعی Workerهای per-tenant، heartbeat و معیارهای ایمنی retries/DLQ.
5. اندازه‌گیری DB performance با index plan، pool، locks و مهاجرت‌های زمان‌بر در PostgreSQL.
6. Runbookهای incident response، on-call، backup/restore/PITR، tabletop و آزمون failover.
7. اجرای همه تست‌ها در CI، آزمون staging و امضای پذیرش مستقل پیش از داده واقعی بیمار.

این مرحله پیش‌نیاز مشاهده اولیه عملیات را فراهم می‌کند اما معیار نهایی پرامپت هنوز پذیرفته نشده است.
