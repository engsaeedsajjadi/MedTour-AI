# انتشار پروژه در GitHub

این بسته شامل مخزن Git محلی با دو کامیت و شاخه `main` است. به دلیل محدودیت ابزار GitHub متصل در جلسه، ایجاد مخزن جدید مستقیماً از این محیط ممکن نبوده است. هیچ مخزن جدیدی در حساب شما ساخته نشده است.

## مراحل با GitHub

1. به https://github.com/new بروید.
2. Owner: `engsaeedsajjadi`
3. Repository name: `MedTour-AI`
4. Visibility: **Private** (پیشنهاد امنیتی؛ پروژه هنوز برای پردازش واقعی پرونده پزشکی آماده نیست).
5. گزینه‌های ایجاد README / .gitignore / License را فعال نکنید، چون در این بسته موجود هستند.
6. گزینه Create repository را بزنید.
7. فایل ZIP کامل را استخراج کنید و در PowerShell، داخل پوشه پروژه، فایل `publish_github.ps1` را اجرا کنید.
8. در صورت درخواست، از روش رسمی Git Credential Manager برای ورود به حساب خود استفاده کنید.

**توجه:** در صورت خطای اعتبارسنجی یا تنظیمات اجرای PowerShell، با دستورهای زیر نیز می‌توانید push کنید:

```powershell
cd "PATH\TO\MedTour-AI"
git remote add origin https://github.com/engsaeedsajjadi/MedTour-AI.git
git push -u origin main
```

از `git push --force` استفاده نکنید.
