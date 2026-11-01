/**
 * Persian presentation layer for codes and API messages.
 * The API keeps stable English identifiers; the interface never shows them raw.
 */

const STATUS:Record<string,string>={
 // case workflow
 new:'جدید',intake:'پذیرش اولیه',documents_pending:'در انتظار مدارک',review_pending:'در انتظار بازبینی',
 provider_review:'بررسی ارائه‌دهنده',quote_pending:'در انتظار پیش‌فاکتور',quote_sent:'پیش‌فاکتور ارسال‌شده',
 confirmed:'تأییدشده',travel_planning:'برنامه‌ریزی سفر',arrived:'رسیده به مقصد',in_treatment:'در حال درمان',
 follow_up:'پیگیری پس از درمان',closed:'بسته‌شده',cancelled:'لغوشده',
 // generic workflow
 draft:'پیش‌نویس',approved:'تأییدشده',superseded:'جایگزین‌شده',requested:'درخواست‌شده',received:'دریافت اداری',
 proposed:'پیشنهادی',internally_confirmed:'تأیید داخلی',internally_allocated:'تخصیص داخلی',open:'باز',
 pending:'در انتظار',pending_review:'در انتظار بررسی',pending_approval:'در انتظار تأیید',pending_human_review:'در انتظار بازبینی انسانی',
 in_review:'در حال بررسی',in_progress:'در حال انجام',assigned:'واگذارشده',resolved:'حل‌شده',completed:'تکمیل‌شده',
 rejected:'ردشده',revoked:'ابطال‌شده',withdrawn:'لغو رضایت',blocked:'مسدود',ready:'آماده',submitted:'ارسال‌شده',
 published:'منتشرشده',sent:'ارسال‌شده',sending:'در حال ارسال',delivered:'تحویل‌شده',read:'خوانده‌شده',
 awaiting_external:'در انتظار طرف خارجی',awaiting_clinician_review:'در انتظار بازبینی پزشک',
 requires_urgent_human_review:'نیازمند بازبینی فوری انسانی',received_for_human_review:'دریافت برای بازبینی انسانی',
 needs_reconciliation:'نیازمند تطبیق',blocked_quality_gate:'متوقف در کنترل کیفیت',blocked_legal_review:'متوقف در بازبینی حقوقی',
 preview_only:'فقط پیش‌نمایش',evaluation:'ارزیابی',attributed:'منتسب‌شده',administratively_reviewed:'بازبینی اداری‌شده',
 administratively_shortlisted:'فهرست کوتاه اداری',approved_internal_only:'تأیید فقط داخلی',
 approved_for_internal_reference:'تأیید برای مرجع داخلی',provider_ack_reported:'اعلام دریافت توسط ارائه‌دهنده',
 provider_contact_reported:'تماس ارائه‌دهنده ثبت شد',provider_decline_reported:'رد توسط ارائه‌دهنده',
 quarantined_no_matching_consent:'قرنطینه — رضایت منطبق ندارد',media_requires_secure_portal:'نیازمند پرتال امن',
 unsupported_text:'متن پشتیبانی‌نشده',
 // evidence and documents
 unverified:'تأییدنشده',verified:'تأییدشده دستی',locally_attested:'گواهی محلی',locally_recorded:'ثبت محلی',
 locally_reviewed:'بازبینی محلی',access_revoked:'دسترسی لغوشده',encrypted_dev_unscanned:'رمزنگاری‌شده — اسکن‌نشده',
 scanned_private_s3:'اسکن‌شده — مخزن خصوصی',erased:'حذف رمزنگاری‌شده',local_encrypted_unscanned_test:'مخزن محلی رمزنگاری‌شده (آزمایشی)',
 // finance
 payment_received:'دریافت وجه',refund_issued:'بازپرداخت',service_expense:'هزینه خدمت',agency_fee:'کارمزد نمایندگی',
 // roles
 admin:'مدیر سازمان',operator:'اپراتور',auditor:'حسابرس',physician:'پزشک',doctor:'پزشک',hospital:'کارمند بیمارستان',
 agent:'نماینده بین‌المللی',patient:'بیمار',
 // consent purposes
 medical_documents:'مدارک پزشکی',communication:'ارتباط با بیمار',ai_processing:'پردازش هوش مصنوعی',
 hospital_coordination:'هماهنگی بیمارستان',visa_coordination:'هماهنگی ویزا',accommodation_coordination:'هماهنگی اقامت',
 transport_coordination:'هماهنگی ترانسفر',interpreter_coordination:'هماهنگی مترجم',agent_referral:'ارجاع نماینده',
 // services
 orthopedics:'ارتوپدی',visa:'ویزا',hotel:'هتل',transport:'ترانسفر',interpreter:'مترجم',home_visit:'ویزیت در منزل',
 airport_pickup:'استقبال فرودگاهی',
 // specialties and service categories
 cardiology:'قلب و عروق',dentistry:'دندان‌پزشکی',diagnostics:'تصویربرداری و تشخیص',neurosurgery:'جراحی مغز و اعصاب',
 oncology:'سرطان‌شناسی',ophthalmology:'چشم‌پزشکی',rehabilitation:'توان‌بخشی',general:'عمومی',other:'سایر',
 hospital_admission:'پذیرش بیمارستان',appointment:'نوبت',appointment_coordination:'هماهنگی نوبت',quote:'پیش‌فاکتور',
 documents:'مدارک',translation:'ترجمه',insurance:'بیمه',travel_coordination:'هماهنگی سفر',general_administrative:'امور اداری عمومی',
 airport_dropoff:'بدرقه فرودگاهی',airport:'فرودگاه',city_transfer:'جابه‌جایی درون‌شهری',city_center:'مرکز شهر',check_in:'پذیرش هتل',
 interpreter_session:'جلسه مترجم',hotel_vendor:'تأمین‌کننده هتل',transport_vendor:'تأمین‌کننده ترانسفر',interpreter_vendor:'تأمین‌کننده مترجم',
 single:'یک‌تخته',double:'دوتخته',accessible:'مناسب افراد کم‌توان',internally_held:'نگه‌داشته داخلی',
 // follow-up outcomes and notifications
 contact_attempted:'تلاش برای تماس',no_response:'بدون پاسخ',human_contact_completed:'تماس انسانی انجام شد',
 additional_information_reported:'اطلاعات تکمیلی ثبت شد',no_longer_needed:'دیگر لازم نیست',followup:'پیگیری',human:'انسانی',
 not_applicable:'موضوعیت ندارد',ready_for_manual_submission:'آماده ارسال دستی',submission_reported:'ارسال ثبت شد',
 issued_reported:'صدور ثبت شد',refused_reported:'رد ثبت شد',case_update_available:'به‌روزرسانی پرونده',
 appointment_update_available:'به‌روزرسانی نوبت',document_reminder:'یادآوری مدارک',please_check_secure_portal:'لطفاً پرتال امن را ببینید',
 greeting:'خوش‌آمدگویی',process:'روند کار',services:'خدمات',contact:'تماس',faq:'پرسش‌های متداول',about:'درباره ما',
 business_contact:'تماس سازمانی',legal:'حقوقی',medical:'پزشکی',request_more_information:'درخواست اطلاعات تکمیلی',
 // settings keys
 brand:'نام تجاری',locale:'زبان پیش‌فرض',timezone:'منطقه زمانی',enabled_languages:'زبان‌های فعال',feature_flags:'قابلیت‌های فعال',
 notification_rules:'قوانین اعلان',service_categories:'دسته‌های خدمت',consent_notice_version:'نسخه اطلاعیه رضایت',public_portal:'پرتال عمومی',
 // languages
 fa:'فارسی',ar:'عربی',en:'انگلیسی',ps:'پشتو',prs:'دری',
 // misc
 true:'بله',false:'خیر',
};

/** Persian label for an API code; unknown codes are humanised, never shown with underscores. */
export function fa(value:unknown):string{
 if(value===null||value===undefined||value==='')return '—';
 const key=String(value);
 if(STATUS[key])return STATUS[key];
 if(STATUS[key.toLowerCase()])return STATUS[key.toLowerCase()];
 return /^[a-z0-9_]+$/.test(key)?key.replace(/_/g,' '):key;
}

const MESSAGES:Record<string,string>={
 'Permission denied':'این بخش برای نقش کاربری شما در دسترس نیست.',
 'Not authenticated':'ابتدا وارد حساب شوید.',
 'Invalid or expired token':'نشست شما منقضی شده است؛ دوباره وارد شوید.',
 'Invalid credentials':'شناسه سازمان، ایمیل یا رمز عبور نادرست است.',
 'Too many login attempts':'تلاش‌های ورود بیش از حد مجاز است؛ چند دقیقه بعد دوباره امتحان کنید.',
 'Rate limiting unavailable':'سرویس کنترل ورود در دسترس نیست؛ کمی بعد تلاش کنید.',
 'Invalid refresh credential':'نشست شما معتبر نیست؛ دوباره وارد شوید.',
 'Refresh replay detected':'برای حفاظت از حساب، نشست بسته شد؛ دوباره وارد شوید.',
 'Invalid MFA code':'کد تأیید دومرحله‌ای نادرست است.',
 'New password must differ':'رمز جدید باید با رمز فعلی متفاوت باشد.',
 'Case not found':'پرونده پیدا نشد.',
 'Patient not found':'بیمار پیدا نشد.',
 'Physician not found':'پزشک پیدا نشد.',
 'Hospital not found':'بیمارستان پیدا نشد.',
 'Staff account not found':'حساب کاربری پیدا نشد.',
 'Record not found':'رکورد پیدا نشد.',
 'Request not found':'درخواست پیدا نشد.',
 'Resource not found':'منبع پیدا نشد.',
 'Version not found':'نسخه پیدا نشد.',
 'Quote not found':'پیش‌فاکتور پیدا نشد.',
 'Coordination not found':'درخواست هماهنگی پیدا نشد.',
 'Document unavailable':'سند در دسترس نیست.',
 'Document not available':'سند در دسترس نیست.',
 'Document not in patient case':'سند متعلق به پرونده این بیمار نیست.',
 'Private encrypted document not available':'سند رمزنگاری‌شده در دسترس نیست.',
 'Intake not found':'فرم پذیرش پیدا نشد.',
 'Intake session not found':'جلسه پذیرش پیدا نشد.',
 'Not found':'مورد درخواستی پیدا نشد.',
 'Not Found':'مورد درخواستی پیدا نشد.',
 'Active intake consent required':'رضایت فعال «پذیرش اولیه» بیمار لازم است.',
 'Current intake consent required':'رضایت فعال «پذیرش اولیه» بیمار لازم است.',
 'Communication consent required':'رضایت فعال «ارتباط با بیمار» لازم است.',
 'Active communication consent required':'رضایت فعال «ارتباط با بیمار» لازم است.',
 'Current communication consent required':'رضایت فعال «ارتباط با بیمار» لازم است.',
 'Active communication and intake consent required':'رضایت‌های فعال «پذیرش اولیه» و «ارتباط با بیمار» لازم است.',
 'Medical document consent is required':'رضایت فعال «مدارک پزشکی» بیمار لازم است.',
 'AI processing consent required':'رضایت فعال «پردازش هوش مصنوعی» لازم است.',
 'Inactive case':'این پرونده بسته یا لغو شده است.',
 'Invalid case workflow transition':'این تغییر وضعیت برای پرونده مجاز نیست.',
 'Idempotency key conflict':'این شناسه درخواست قبلاً با اطلاعات دیگری ثبت شده است.',
 'Timezone offset required':'زمان باید همراه منطقه زمانی وارد شود.',
 'Invalid appointment window':'بازه زمانی نوبت معتبر نیست (آینده، حداکثر ۴ ساعت).',
 'No matching proposed availability':'ظرفیت پیشنهادی پزشک این بازه را پوشش نمی‌دهد.',
 'Overlapping internal appointment allocation':'این بازه با نوبت دیگری هم‌پوشانی دارد.',
 'Overlapping proposed slot':'این ظرفیت با ظرفیت ثبت‌شده دیگری هم‌پوشانی دارد.',
 'Appointment not pending':'این نوبت دیگر در انتظار بررسی نیست.',
 'Resource conflict':'تداخل منابع؛ بازه دیگری انتخاب کنید.',
 'Managed appointment not found':'نوبت پیدا نشد.',
 'Use the appointment-calendar review workflow':'این نوبت فقط از تقویم نوبت‌دهی قابل تغییر است.',
 'Current locally attested physician evidence required':'مدرک معتبر و ثبت‌شده پزشک لازم است.',
 'Physician must be manually verified first':'ابتدا مدرک پزشک باید دستی تأیید شود.',
 'Availability must be a future 1-8 hour window within 365 days':'ظرفیت باید بازه‌ای ۱ تا ۸ ساعته در یک سال آینده باشد.',
 'Base quote cannot be changed':'این پیش‌فاکتور قفل است و تغییر نمی‌کند.',
 'Approved snapshot is immutable':'نسخه تأییدشده قابل تغییر نیست.',
 'Cannot change approved quotation':'پیش‌فاکتور تأییدشده قابل تغییر نیست.',
 'Not approvable':'این نسخه قابل تأیید نیست.',
 'Only latest revision may be approved':'فقط آخرین نسخه قابل تأیید است.',
 'Only draft quotes can be approved':'فقط پیش‌فاکتور پیش‌نویس قابل تأیید است.',
 'Only approved snapshots can be exported':'فقط نسخه تأییدشده خروجی PDF دارد.',
 'Manual sourced FX approval required':'برای ارز متفاوت، نرخ ارز مستند لازم است.',
 'Price source not found':'منبع قیمت پیدا نشد.',
 'Expired price source':'اعتبار منبع قیمت تمام شده است.',
 'Underlying price has expired':'اعتبار قیمت پایه تمام شده است.',
 'Positive total required':'مجموع باید بیشتر از صفر باشد.',
 'Invalid currency':'کد ارز معتبر نیست.',
 'Use ISO currency code':'کد ارز را به‌صورت استاندارد سه‌حرفی وارد کنید.',
 'Existing manual quote amount must be reconciled before managed versions':'مبلغ دستی قبلی باید پیش از نسخه‌بندی تطبیق داده شود.',
 'Request cannot be acknowledged':'این درخواست قبلاً ثبت دریافت شده یا قابل ثبت نیست.',
 'Medical document storage is disabled':'مخزن مدارک پزشکی غیرفعال است.',
 'Approved medical document storage is disabled':'مخزن تأییدشده مدارک پزشکی غیرفعال است.',
 'Approved medical file storage and scanner are not configured':'مخزن امن و اسکنر فایل پیکربندی نشده‌اند.',
 'Only PDF, JPEG and PNG contents are accepted':'فقط فایل PDF، JPEG یا PNG پذیرفته می‌شود.',
 'Document exceeds 8 MiB':'حجم فایل بیش از ۸ مگابایت است.',
 'Empty document':'فایل خالی است.',
 'Payload too large':'حجم داده ارسالی بیش از حد مجاز است.',
 'Patient access required':'برای دیدن این بخش وارد پرتال بیمار شوید.',
 'Invalid patient access':'دسترسی شما به پرتال معتبر نیست؛ دعوت جدید دریافت کنید.',
 'Patient access expired':'نشست پرتال شما تمام شده است؛ دعوت جدید دریافت کنید.',
 'Portal access consent no longer active':'رضایت لازم برای پرتال لغو شده است.',
 'Invalid or used invitation':'لینک دعوت نامعتبر است یا قبلاً استفاده شده است.',
 'Invitation expired':'اعتبار لینک دعوت تمام شده است.',
 'Invalid verification code':'کد شش‌رقمی نادرست است.',
 'Patient portal consent unavailable':'رضایت لازم برای پرتال فعال نیست.',
 'Too many patient invitation requests':'تعداد دعوت‌ها در این ساعت بیش از حد مجاز است.',
 'Invalid or consumed link':'لینک رضایت نامعتبر است یا قبلاً استفاده شده است.',
 'Expired consent link':'اعتبار لینک رضایت تمام شده است.',
 'Unsupported language':'این زبان پشتیبانی نمی‌شود.',
 'Unsupported locale':'این زبان پشتیبانی نمی‌شود.',
 'Invalid JSON':'داده ارسالی معتبر نیست.',
 'JSON required':'داده ارسالی معتبر نیست.',
 'Setting key is not allowed':'این تنظیم قابل تغییر نیست.',
 'Setting value must be an object':'مقدار تنظیم باید ساختار JSON داشته باشد.',
 'Invalid status':'وضعیت معتبر نیست.',
 'Bad status':'وضعیت معتبر نیست.',
 'Invalid appointment state':'وضعیت نوبت اجازه این تغییر را نمی‌دهد.',
 'Required stack dependency unavailable':'یکی از سرویس‌های پشتیبان در دسترس نیست.',
 'Two-factor authentication required':'برای ادامه، ورود دومرحله‌ای حساب خود را فعال و تأیید کنید.',
 'Proposed availability is no longer active':'ظرفیت پزشک برای این نوبت لغو شده است؛ نوبت قابل تأیید نیست.',
 'Document is under legal hold':'این سند در توقیف قانونی است و قابل حذف نیست.',
 'Document is not due for erasure: revoke access or wait for the retention period':'این سند هنوز قابل حذف نیست؛ ابتدا دسترسی لغو شود یا دوره نگهداری به پایان برسد.',
 'Document already erased':'این سند قبلاً حذف رمزنگاری‌شده است.',
 'Approved OTP delivery provider is not configured':'سرویس ارسال کد یک‌بارمصرف پیکربندی نشده است.',
 'Patient contact is not a valid address for the configured delivery channel':'اطلاعات تماس بیمار برای ارسال کد معتبر نیست؛ ایمیل یا شماره موبایل را اصلاح کنید.',
 'One-time code delivery failed; try again later':'ارسال کد ناموفق بود؛ کمی بعد دوباره تلاش کنید.',
 'Independent patient identity and approved OTP delivery not configured':'ارسال امن کد ورود بیمار پیکربندی نشده است.',
};

const KEYWORDS:[RegExp,string][]=[
 [/not found|unavailable$/i,'مورد درخواستی پیدا نشد یا در دسترس نیست.'],
 [/consent/i,'رضایت فعال بیمار برای این عملیات لازم است.'],
 [/expired/i,'اعتبار این مورد تمام شده است.'],
 [/not (approved|configured)|disabled|unavailable|provider/i,'این قابلیت در محیط فعلی فعال نیست.'],
 [/active appointment/i,'این ظرفیت نوبت فعال دارد؛ ابتدا نوبت‌ها را لغو کنید.'],
 [/overlap|conflict/i,'این درخواست با مورد دیگری تداخل دارد.'],
 [/required/i,'اطلاعات لازم کامل نیست.'],
 [/invalid|unsupported|unknown|must/i,'اطلاعات وارد‌شده معتبر نیست.'],
];

const BY_STATUS:Record<number,string>={
 400:'درخواست معتبر نیست.',401:'نشست شما معتبر نیست؛ دوباره وارد شوید.',403:'این بخش برای نقش کاربری شما در دسترس نیست.',
 404:'مورد درخواستی پیدا نشد.',409:'این عملیات با وضعیت فعلی سازگار نیست.',413:'حجم داده بیش از حد مجاز است.',
 415:'نوع فایل پذیرفته نمی‌شود.',422:'اطلاعات وارد‌شده معتبر نیست.',429:'تعداد درخواست‌ها زیاد است؛ کمی بعد تلاش کنید.',
 500:'خطای داخلی سامانه؛ دوباره تلاش کنید.',502:'سرویس بیرونی پاسخ نداد.',503:'این سرویس فعلاً در دسترس نیست.',
};

const FIELD:Record<string,string>={
 full_name:'نام کامل',email:'ایمیل',password:'رمز عبور',phone:'تلفن',country:'کشور',language:'زبان',
 case_id:'پرونده',patient_id:'بیمار',physician_id:'پزشک',hospital_id:'بیمارستان',currency:'ارز',
 amount_minor:'مبلغ',units:'تعداد',reference:'مرجع',starts_at:'زمان شروع',ends_at:'زمان پایان',
 details:'توضیحات',label:'عنوان',source:'منبع',valid_until:'تاریخ اعتبار',role:'نقش',status:'وضعیت',
 tenant_slug:'شناسه سازمان',
};

type ValidationItem={loc?:unknown[];msg?:string;type?:string};

/** Persian message for an API error body; never returns raw English API text. */
export function faError(detail:unknown,status:number):string{
 if(Array.isArray(detail)){
  const first=detail[0] as ValidationItem|undefined;
  const field=first?.loc?.filter(x=>typeof x==='string'&&x!=='body'&&x!=='query').pop() as string|undefined;
  const name=field?(FIELD[field]||fa(field)):'';
  if(first?.type==='missing')return name?`فیلد «${name}» ضروری است.`:'فیلدهای ضروری را کامل کنید.';
  if(first?.type==='json_invalid')return 'داده ارسالی معتبر نیست.';
  if(first?.type?.includes('too_long'))return name?`متن «${name}» بیش از حد طولانی است.`:'متن بیش از حد طولانی است.';
  if(first?.type?.startsWith('greater_than')||first?.type?.startsWith('less_than'))return name?`مقدار «${name}» خارج از محدوده مجاز است.`:'مقدار خارج از محدوده مجاز است.';
  return name?`مقدار «${name}» معتبر نیست.`:'اطلاعات وارد‌شده معتبر نیست.';
 }
 if(typeof detail==='string'){
  if(MESSAGES[detail])return MESSAGES[detail];
  if(/[؀-ۿ]/.test(detail))return detail;
  if(status===403)return BY_STATUS[403];
  for(const [pattern,text] of KEYWORDS)if(pattern.test(detail))return text;
 }
 return BY_STATUS[status]||'خطایی رخ داد؛ دوباره تلاش کنید.';
}

/** Turns technical fetch failures into a Persian message. */
export function faNetwork(error:unknown):string{
 const message=error instanceof Error?error.message:String(error);
 if(/[؀-ۿ]/.test(message))return message;
 if(/fetch|network|load failed/i.test(message))return 'ارتباط با سرور برقرار نشد؛ اتصال را بررسی کنید.';
 return 'خطایی رخ داد؛ دوباره تلاش کنید.';
}

/** Visual tone for a status badge: '' (positive/neutral), 'warn', 'danger' or 'muted'. */
export function tone(value:unknown):string{
 const v=String(value??'');
 if(/cancel|reject|revok|blocked|decline|withdrawn|quarantin|failed/.test(v))return 'danger';
 if(/pending|requested|draft|unverified|unscanned|review|awaiting|proposed|in_progress|needs/.test(v))return 'warn';
 if(/superseded|closed|preview|unsupported/.test(v))return 'muted';
 return '';
}

const CODE_KEYS=new Set(['status','role','license_status','credential_status','entry_type','service_type','language','purpose','kind','action','evidence_status','legacy_directory_status','category','specialty','service_code']);
const DATE_KEYS=/(_at|_until|^date|_date)$/;

/** Formats one table cell for display: codes in Persian, dates in the Persian calendar, booleans as بله/خیر. */
export function cell(key:string,value:unknown):string{
 if(value===null||value===undefined||value==='')return '—';
 if(typeof value==='boolean')return fa(value);
 if(CODE_KEYS.has(key))return fa(value);
 if(DATE_KEYS.test(key)&&typeof value==='string'){const d=new Date(value);if(!Number.isNaN(d.getTime()))return d.toLocaleString('fa-IR',{dateStyle:'medium',timeStyle:'short'});}
 if(/amount|total|units|count/.test(key)&&typeof value==='number')return value.toLocaleString('fa-IR');
 return String(value);
}
