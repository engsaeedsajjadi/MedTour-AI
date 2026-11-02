# بخش ۳۶ — Testing & Quality Assurance

## وضعیت
تست‌های امنیتی مصنوعی و CI مستقل برای کنترل‌های پایه اضافه شدند. **این مرحله به‌معنای تکمیل همه الزامات QA یا تأیید قابلیت استفاده Production نیست.** در این جلسه هیچ یک از تست‌ها به‌صورت واقعی اجرا و سبز بودن آن‌ها تأیید نشده است.

## آزمون‌های جدید
- `backend/tests/test_section_36_quality_gates.py`: وضعیت health بدون ادعای Production؛ بررسی 401/403 برای API خصوصی؛ security headers؛ جداسازی بیماران و پرونده‌ها برای دو Tenant؛ عدم بازتاب گذرواژه در پاسخ ورود.
- `backend/tests/test_section_36_delivery_contract.py`: بررسی ثابت ماندن مراحل pytest، migration واقعی PostgreSQL، probe کنترل RLS، frontend npm audit/typecheck/build و گیت ایمنی Alpha.
- `.github/workflows/section36-quality.yml`: CI مستقل برای تست‌های بالا با محیط SQLite مصنوعی و secret صرفاً آزمایشی.
- تست‌های قدیمی backend، PostgreSQL+Redis، schema migration، RLS و frontend CI حذف یا جایگزین نشده‌اند.

## اجرای محلی
```powershell
git fetch origin
git switch feature/section-36-quality-gates
docker compose up -d --build
docker compose exec api pytest -q tests/test_section_36_quality_gates.py tests/test_section_36_delivery_contract.py
docker compose exec api pytest -q
```
قبل از اجرای `docker compose up` روی دیتابیس با داده‌های ارزشمند نسخه پشتیبان معتبر بگیرید. برای اجرای فقط تست‌ها بدون تغییر DB اصلی، از محیط تست ایزوله استفاده کنید.

## موارد پذیرش کامل بخش ۳۶ که هنوز باقی مانده‌اند
1. Unit/Integration/Contract تست همه ماژول‌ها در PostgreSQL با tenant principals واقعی؛ کنترل Race/Deadlock/Concurrency.
2. E2E مرورگر برای ادمین، پزشک، بیمار و زبان‌های FA/EN/AR/PS/PRS؛ بررسی دسترس‌پذیری WCAG.
3. تست بار و soak، شاخص‌های latency و throughput، ظرفیت همزمان و محدودیت منابع با داده مصنوعی.
4. OWASP ASVS، SAST/SCA، اسکن تصویر، DAST و آزمون نفوذ مستقل، کنترل injection و IDOR.
5. Fault injection برای Redis، PostgreSQL، شبکه، Provider، Webhook و حالت unknown delivery؛ آزمون idempotency و recovery.
6. Chaos/backup/restore/PITR و تست RPO/RTO و صحت عدم نشت داده بین Tenantها.
7. سنجش coverage واقعی با threshold مورد توافق تیم و ایجاد artifactهای قابل حسابرسی.
8. آزمون واقعی اتصال پیام‌رسان پس از اخذ مجوز و تأیید privacy/clinical و قوانین منطقه‌ای.
9. UAT کارفرما، چک‌لیست release و sign-off مستقل مسئول امنیت و داده پزشکی.

### وضعیت انتشار
تغییرات فقط در شاخه توسعه و PR بررسی‌نشده قرار می‌گیرند. **هیچ داده واقعی بیمار یا استقرار تجاری مجاز نشده است.**
