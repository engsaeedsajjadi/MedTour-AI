# بخش ۳۳ — API Architecture & Integration

## وضعیت پیاده‌سازی
قرارداد نسخه API و Request Correlation در شاخه بخش ۳۳ اضافه شده است. این اقدام **تمام نیازهای API Enterprise را کامل نمی‌کند**: نرخ‌دهی سراسری، idempotency تمام عملیات، gateway، قراردادهای external integration، امنیت عملیاتی و پایش تولیدی هنوز باقی‌اند.

### پایه‌های موجود
FastAPI، مسیرهای `/api/v1`، مدل‌های Pydantic، احراز هویت JWT، RBAC، کنترل Tenant، محدودسازی تلاش ورود، OpenAPI خودکار و idempotency برخی endpointهای حساس از قبل موجودند.

### خروجی جدید
- `GET /api/v1/meta/contract`: نسخه اصلی ۱، URL ساختار OpenAPI، وضعیت Alpha، اعلام پوشش محدود idempotency و ممنوعیت داده واقعی بیمار.
- هدر `X-API-Major-Version: 1` در پاسخ‌ها.
- هدر `X-Request-ID` با مقدار تصادفی و مستقل در هر پاسخ. شناسه ارسالی کاربر نادیده گرفته می‌شود و سرور آن را برای جلوگیری از جعل یا تزریق داده بازتاب نمی‌دهد.
- `backend/tests/test_section_33_api_contract.py` برای کنترل قرارداد، وجود OpenAPI، شناسه غیرقابل‌اعتماد ورودی و پاسخ 401.
- سازگاری نسخه ۱ بدون تغییر رفتار مسیرهای موجود حفظ می‌شود؛ این ویژگی به‌تنهایی logging یا tracing توزیع‌شده را فعال نمی‌کند.

### تست محلی
```powershell
git fetch origin
git switch feature/section-33-api-contract
docker compose up -d --build
docker compose exec api pytest -q tests/test_section_33_api_contract.py
```
تست‌ها نوشته شده‌اند اما در این جلسه اجرا نشده‌اند.

### موارد باقی‌مانده پرامپت
1. قرارداد API نسخه‌دار برای همه endpointها و مستندات تغییرات breaking/non-breaking.
2. پاسخ خطای یکپارچه با فیلدهای استاندارد code/message/request_id و حذف اطلاعات حساس.
3. rate limiting چندسطحی و قابل‌اعتماد با Redis، سیاست fail-closed و حفاظت از APIهای عمومی.
4. idempotency سراسری برای عملیات تغییر‌دهنده با کلیدهای tenant/user/path/body، قفل تراکنشی و TTL.
5. Webhook signature، replay protection، rotate secrets، allowlist و اعتبارسنجی payload برای همه سرویس‌های خارجی.
6. timeout، circuit breaker، backoff، DLQ و reconciliation بدون دوباره‌اجرای عملیات مالی/بالینی.
7. OpenTelemetry، metricهای RED، لاگ بدون PHI، alert و request correlation end-to-end.
8. contract test و integration test واقعی PostgreSQL/Redis، تست بار و نفوذ و تأیید امنیت بیرونی.

**درگاه‌های واقعی پزشکی، مالی و پیام‌رسان تنها پس از قرارداد و مجوز مناسب قابل راه‌اندازی‌اند.**
