# بخش ۲۵ — پردازش پیام صوتی چندزبانه STT/TTS

**دامنه اجرا:** زیرساخت واقعی تماس API صوتیِ OpenAI-compatible به‌شکل opt-in، اعتبارسنجی و تبدیل WAV/OGG-Opus، رابط پنج‌زبانه برای بارگذاری فایل **کاملاً ساختگی**، بازبینی متن و پیش‌شنوایی گفتار ثابت. **اتصال دریافت خودکار پیام صوتی واتساپ/تلگرام یا استفاده از صدای واقعی بیمار انجام نشده است.**

## اصل امنیت و حفاظت داده
نسخه MedTour AI در محیط Alpha هنوز مجوز پردازش اطلاعات پزشکی واقعی بیمار را ندارد. مسیرهای صوتی به `APP_ENV=development/test` محدود شده‌اند. درخواست صوتی فقط برای حساب admin/operator معتبر است؛ برای STT باید `synthetic_sample_only=true` را صریحاً انتخاب کرد. هیچ ورودی `patient_id`، `case_id`، متن دلخواه برای TTS یا لینک arbitrary provider پذیرفته نمی‌شود.

**هیچ صوت ورودی، خروجی یا متن تشخیص‌داده‌شده در DB ذخیره نمی‌شود.** فقط شناسه درخواست، tenant، نوع عملیات، زبان، قالب، مدت فایل، هش SHA-256 صدا و متن، نویسنده، تصمیم بازبین و زمان در `voice_sample_jobs` نگهداری می‌شوند. متن STT تنها در پاسخ نخست بازگردانده می‌شود و تکرار درخواست همان کلید صرفاً وضعیت و هش را می‌دهد، نه متن را؛ درخواست‌ها و صوت نباید در لاگ/تله‌متری ضبط شوند. صوت خروجی TTS برای پیش‌شنوایی با `Cache-Control: no-store, private` و بدون ذخیره سمت سرور بازگردانده می‌شود.

## فرمت‌های ورودی و decode
- `WAV` با `RIFF` واقعی، mono، PCM16 و نرخ نمونه‌برداری 8000، 16000، 24000 یا 48000 هرتز.
- `OGG/Opus` فقط با شناسه `OggS` و `OpusHead` معتبر؛ تبدیل با FFmpeg سمت سرور به PCM16 mono 16kHz. Dockerfile اکنون FFmpeg را در ایمیج Backend نصب می‌کند.
- سقف حجم ورودی 1,000,000 بایت، خروجی خام decode حداکثر 1,100,000 بایت و مدت ۳۰ ثانیه؛ decoder با timeout نه‌ثانیه‌ای اجرا می‌شود. فرمت WebM، MP3، AAC، μ-law تلفنی یا رمزگشایی مستقیم فایل‌های رمز‌شده پیام‌رسان هنوز پشتیبانی نشده‌اند.
- دریافت از سرویس‌های خارجی یا decrypt رسانه واتساپ/تلگرام در این بخش پیاده‌سازی نشده‌اند؛ فایل ساختگی باید به‌شکل محلی بارگذاری شود.

## پنج زبان
`fa` فارسی، `ar` عربی، `en` انگلیسی، `ps` پشتو، `prs` دری. در `voice_provider.py` اشاره زبان درخواست STT برای دری `fa` است، چون بسیاری از APIهای رایج کد اختصاصی دری ندارند. **کیفیت زبانی، لهجه‌ای و اصطلاحات پزشکی برای دری و پشتو مستقلاً تأیید نشده و نباید به‌عنوان توانایی آزموده‌شده واقعی عرضه شود.** برای هر زبان و STT/TTS باید قابلیت از طریق تنظیمات allowlist مستقل فعال شود.

## اتصال ارائه‌دهنده (پیش‌فرض خاموش)
متغیرهای محیطی لازم برای آزمایش با **داده ساختگی**:

```dotenv
APP_ENV=development
AI_PROVIDER_APPROVED=true
VOICE_PROCESSOR_APPROVED=true
AI_API_KEY=YOUR_PROVIDER_KEY
AI_BASE_URL=https://your-approved-provider.example/v1
AI_APPROVED_HOSTS=your-approved-provider.example
VOICE_STT_ENABLED=true
VOICE_TTS_ENABLED=true
VOICE_STT_MODEL=YOUR_SUPPORTED_STT_MODEL
VOICE_TTS_MODEL=YOUR_SUPPORTED_TTS_MODEL
VOICE_VERIFIED_STT_LOCALES=fa,en
VOICE_VERIFIED_TTS_LOCALES=fa,en
```

متغیرهای فوق تنها نمونه چگونگی فعال‌سازی‌اند، **نه ادعای تأیید رسمی DPA یا توانایی زبانی مدل**. حتی در صورت فعال‌سازی، درخواست STT باید synthetic باشد. آدرس باید HTTPS و در فهرست میزبان‌های صریح باشد و Redirect دنبال نمی‌شود. API از `POST /audio/transcriptions` با multipart و `POST /audio/speech` با WAV استفاده می‌کند؛ سازگاری هر ارائه‌دهنده باید با تست واقعی مستقل بررسی شود. مدل‌های بدون پشتیبانی این APIها 502 خواهند داشت.

## REST و رابط
- `GET /api/v1/voice/readiness`: آمادگی STT/TTS هر زبان، مرزهای codec و اعلام غیرفعال بودن کانال‌های واقعی
- `POST /api/v1/voice/transcribe`: multipart شامل `file`، `locale`، `request_key` و `synthetic_sample_only=true`. متن اولیه فقط یک بار در پاسخ JSON و وضعیت `pending_human_review` ظاهر می‌شود.
- `POST /api/v1/voice/drafts/{id}/review`: فقط admin متفاوت از تولیدکننده، تطبیق متن دقیق با هش قبلی و مرجع غیرحساس بررسی؛ نتیجه فقط `approved_internal_only` یا `rejected`. **این تأیید مجوز ارسال یا تصمیم بالینی نیست.**
- `GET /api/v1/voice/drafts`: فهرست فقط متادیتای همان tenant بدون صوت یا متن STT.
- `POST /api/v1/voice/speak`: فقط `locale`، `intent` از مجموعه پیام‌های اداری ثابت `receptionist.RESPONSES` و `synthetic_sample_only=true` را می‌پذیرد؛ WAV خروجی برای پیش‌شنوایی داخلی می‌دهد و هرگز به بیمار ارسال نمی‌شود.

پنل فارسی: `http://localhost:3000/voice` — آپلود نمونه ساختگی، مشاهده متن موقت، وضعیت راه‌اندازی زبان، شنیدن TTS ثابت و بازبینی داخلی. نشست باید معتبر باشد. بعد از بستن یا بارگذاری مجدد صفحه، متن خام را نمی‌توان از DB بازیابی کرد.

## تست و نحوه اجرا
`backend/tests/test_section_25_voice.py` و `backend/tests/test_section_25_voice_provider.py` تست‌های codec، مدت، اندازه، امضای فایل، پنج زبان، بازبینی مستقل، جلوگیری از ارسال خودکار، tenant isolation، idempotency، fail closed و قرارداد واقعی endpointهای STT/TTS با provider mock را پوشش می‌دهند. اجرای واقعی API ارائه‌دهنده بدون پیکربندی معتبر قابل ادعا نیست.

```powershell
git pull origin main
docker compose up -d --build
docker compose exec api alembic upgrade head
```

## موارد باقی‌مانده قبل از فروش و اتصال واقعی
ارزیابی حقوقی DPA و پردازش صوت پزشکی، رضایت مخصوص ضبط و AI، ذخیره‌سازی رمز‌شده و retention/erasure، webhook authenticated و decrypt قانونی رسانه پیام‌رسان، اسکن بدافزار و codec sandboxing، پردازش غیرهم‌زمان و retry/circuit breaker، STT/TTS واقعی آزموده‌شده برای پنج زبان، شناسایی خطای پزشکی، کیفیت تفسیر زبانی، فایل‌های طولانی و streaming/telephony، هزینه واقعی مدل‌ها و پایش ممیزی مستقل.

**مهم:** این بخش خروجی پزشک/اورژانس یا توانایی دریافت صدای بیمار را تأیید نمی‌کند. هر کار بالینی و ارسال خارجی نیاز به بازبینی متخصص انسانی و مجوزهای جداگانه دارد.
