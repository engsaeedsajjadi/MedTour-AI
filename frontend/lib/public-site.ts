// Section 22: server-only, published-only public website data.
export const PUBLIC_LOCALES=['fa','ar','en','ps','prs'] as const;
export type PublicLocale=typeof PUBLIC_LOCALES[number];
export type PublicTranslation={title:string;locale:PublicLocale;slug:string;summary:string};
export type SiteEntry={slug:string;translations:Partial<Record<PublicLocale,PublicTranslation>>};
export type PublicManifest={
 tenant_slug:string;locales:PublicLocale[];pages:SiteEntry[];required_slugs:string[];
 missing_translations:Record<PublicLocale,string[]>;all_languages_complete:boolean;
 indexing_opt_in:boolean;legal_review_self_attested:boolean;search_indexing_allowed:boolean;
 independent_legal_approval_verified:boolean;clinical_provider_verified:boolean;
 accepts_real_patient_information:boolean;disclosure:string;
};
export type PublicPage={title:string;body:string;locale:string;slug:string};

export function isLocale(s:string):s is PublicLocale{
 return s==='fa'||s==='ar'||s==='en'||s==='ps'||s==='prs';
}
export function isTenant(s:string){
 return /^[a-z0-9](?:[a-z0-9-]{0,62})$/.test(s);
}
export function isSlug(s:string){
 return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(s);
}
export function publicPath(tenant:string,locale:PublicLocale,slug?:string){
 return '/public/'+encodeURIComponent(tenant)+'/'+encodeURIComponent(locale)+(slug?'/'+encodeURIComponent(slug):'');
}
export const UI:Record<PublicLocale,{
 brand:string;tagline:string;nav:Record<string,string>;heroTitle:string;heroLine:string;
 start:string;learn:string;badge:string;intro:string;heroStat1:string;heroStat2:string;
 stepsTitle:string;servicesTitle:string;legalTitle:string;legalText:string;
 language:string;missing:string;notVerified:string;footer:string;stepDescriptions:string[];
}> = {
 fa:{
 brand:'MedTour AI',tagline:'هماهنگی مسئولانه سفر درمانی',nav:{about:'درباره ما',services:'خدمات',process:'فرایند',faq:'پرسش‌ها',contact:'ارتباط',privacy:'حریم خصوصی',terms:'شرایط', 'medical-disclaimer':'توضیحات پزشکی'},
 heroTitle:'مسیر روشن‌تر برای هماهنگی سفر درمانی',
 heroLine:'اطلاعات عمومی چندزبانه درباره مراحل اداری، درخواست ملاقات و هماهنگی سفر. هر تصمیم درمانی فقط با متخصص واجد صلاحیت و هر خدمت با تأیید انسانی انجام می‌شود.',
 start:'مراحل هماهنگی را ببینید',learn:'آشنایی با خدمات',badge:'هماهنگی انسانی — بدون رزرو خودکار',
 intro:'فرایندی شفاف، انسانی و مبتنی بر رضایت آگاهانه؛ بدون وعده درمان یا نتایج قطعی.',
 heroStat1:'پنج زبان اصلی',heroStat2:'بررسی انسانی الزامی',
 stepsTitle:'همراه مسیر، بدون ادعای پزشکی',servicesTitle:'حوزه‌های هماهنگی اداری',
 legalTitle:'شفافیت و حفاظت از اطلاعات',legalText:'مدارک پزشکی و اطلاعات شخصی فقط پس از ثبت رضایت و از طریق پرتال امن بیمار دریافت می‌شوند؛ آن‌ها را از طریق پیام‌رسان یا ایمیل نفرستید.',
 language:'زبان',missing:'این محتوا هنوز برای این زبان تأیید و منتشر نشده است.',notVerified:'محتوای معرفی؛ نتیجه درمان تضمین نمی‌شود.',
 footer:'هماهنگی اداری سفر درمانی؛ ارائه‌دهنده خدمات درمانی نیستیم. در فوریت‌ها به اورژانس محلی مراجعه کنید.',
 stepDescriptions:['آشنایی با اطلاعات عمومی','رضایت و احراز هویت مستقل','بررسی انسانی درخواست','هماهنگی با ارائه‌دهنده تأییدشده']
 },
 ar:{
 brand:'MedTour AI',tagline:'تنسيق مسؤول للسفر العلاجي',nav:{about:'من نحن',services:'الخدمات',process:'الخطوات',faq:'الأسئلة',contact:'التواصل',privacy:'الخصوصية',terms:'الشروط','medical-disclaimer':'تنبيه طبي'},
 heroTitle:'خطوات أوضح لتنسيق السفر العلاجي',
 heroLine:'معلومات عامة بلغات متعددة حول التنسيق الإداري والمواعيد والسفر. القرارات الطبية للأطباء المؤهلين حصراً؛ كل خدمة تحتاج مراجعة بشرية مستقلة.',
 start:'استعرض الخطوات',learn:'تعرّف على الخدمات',badge:'تنسيق بشري — دون حجوزات تلقائية',
 intro:'تنسيق شفاف بموافقة واعية ومتابعة بشرية؛ بلا وعود أو ضمانات علاجية.',
 heroStat1:'خمس لغات رئيسية',heroStat2:'مراجعة بشرية إلزامية',
 stepsTitle:'مرافقة إدارية، دون ادعاء طبي',servicesTitle:'مجالات التنسيق الإداري',
 legalTitle:'الشفافية وخصوصية البيانات',legalText:'تُستلم الوثائق الصحية والبيانات الشخصية فقط بعد تسجيل الموافقة وعبر بوابة المريض الآمنة؛ لا ترسلها عبر تطبيقات المراسلة أو البريد الإلكتروني.',
 language:'اللغة',missing:'هذه الصفحة لم تتم مراجعتها ونشرها بهذه اللغة.',notVerified:'محتوى تعريفي؛ لا تُضمن نتائج العلاج.',
 footer:'تنسيق إداري للسفر العلاجي؛ لسنا مقدّمي رعاية طبية. للحالات العاجلة اتصل بخدمات الطوارئ المحلية.',
 stepDescriptions:['معلومات عامة','تحقق مستقل من الهوية والموافقة','مراجعة بشرية للطلب','تنسيق مع شريك معتمد']
 },
 ps:{
 brand:'MedTour AI',tagline:'د روغتيايي سفر مسؤوله همغږي',
 nav:{about:'زموږ په اړه',services:'خدمتونه',process:'پړاوونه',faq:'پوښتنې',contact:'اړيکه',privacy:'محرمیت',terms:'شرطونه','medical-disclaimer':'طبي خبرتیا'},
 heroTitle:'د طبي سفر د همغږۍ لپاره روښانه لاره',
 heroLine:'په څو ژبو د غير طبي همغږۍ، ملاقات غوښتنو او سفر په اړه عمومي معلومات. طبي پرېکړې يوازې وړ متخصصان کوي او هر ريښتينی خدمت انساني تاييد ته اړتيا لري.',
 start:'پړاوونه وګورئ',learn:'د خدمتونو پېژندنه',badge:'انساني همغږي — اتوماتيک ریزرف نشته',
 intro:'روڼ معلومات، انساني ارزونه او باخبره رضايت؛ د درملنې هېڅ تضمين نشته.',
 heroStat1:'پنځه ژبې',heroStat2:'انساني ارزونه اړينه ده',
 stepsTitle:'اداري مرسته، نه طبي مشوره',servicesTitle:'د اداري همغږۍ برخې',
 legalTitle:'روڼتيا او د معلوماتو ساتنه',legalText:'طبي اسناد او شخصي معلومات يوازې د رضايت تر ثبت وروسته او د ناروغ د خوندي پورټل له لارې ترلاسه کېږي؛ هغه په پيغام رسانونو يا برېښناليک کې مه لېږئ.',
 language:'ژبه',missing:'د دې ژبې محتوا لا نه ده ارزول شوې او خپره شوې.',notVerified:'معرفي معلومات؛ د درملنې پايله نه تضمینېږي.',
 footer:'د روغتيايي سفر اداري همغږي؛ موږ طبي خدمت نه وړاندې کوو. په بيړني حالت کې ځايي عاجلو خدمتونو ته زنګ ووهئ.',
 stepDescriptions:['عمومي معلومات ولولئ','هويت او رضايت خپلواک تاييد کړئ','د انسان له خوا غوښتنه وڅېړئ','له تاييد شوي شریک سره همغږي']
 },
 prs:{
 brand:'MedTour AI',tagline:'هماهنگی مسئولانه سفر صحی',
 nav:{about:'درباره ما',services:'خدمات',process:'مراحل',faq:'پرسش‌ها',contact:'تماس',privacy:'محرمیت',terms:'شرایط','medical-disclaimer':'توضیحات طبی'},
 heroTitle:'راه روشن‌تر برای هماهنگی سفر صحی',
 heroLine:'معلومات عمومی چندزبانه درباره هماهنگی اداری، درخواست وقت و سفر. تصمیم طبی صرف با داکتر واجد شرایط و انجام خدمت واقعی تنها پس از تأیید انسانی صورت می‌گیرد.',
 start:'دیدن مراحل هماهنگی',learn:'آشنایی با خدمات',badge:'هماهنگی انسانی — بدون ریزرف خودکار',
 intro:'معلومات شفاف، بررسی انسانی و رضایت آگاهانه؛ بدون تضمین نتیجه تداوی.',
 heroStat1:'پنج زبان اصلی',heroStat2:'بررسی انسانی ضروری است',
 stepsTitle:'راهنمایی اداری، نه مشوره طبی',servicesTitle:'زمینه‌های هماهنگی غیرطبی',
 legalTitle:'شفافیت و حفاظت معلومات',legalText:'اسناد صحی و معلومات شخصی تنها پس از ثبت رضایت و از طریق پورتال مصون بیمار دریافت می‌شوند؛ آن‌ها را از طریق پیام‌رسان یا ایمیل نفرستید.',
 language:'زبان',missing:'این صفحه هنوز به این زبان بررسی و نشر نشده است.',notVerified:'محتوای معرفی؛ نتیجه تداوی تضمین نمی‌شود.',
 footer:'هماهنگی اداری سفر صحی؛ ما ارائه‌دهنده خدمات طبی نیستیم. در حالت عاجل به خدمات عاجل محلی مراجعه کنید.',
 stepDescriptions:['مرور معلومات عمومی','تأیید مستقل هویت و رضایت','بررسی انسانی درخواست','هماهنگی با ارائه‌دهنده تأییدشده']
 },
 en:{
 brand:'MedTour AI',tagline:'Responsible medical travel coordination',nav:{about:'About',services:'Services',process:'Process',faq:'FAQ',contact:'Contact',privacy:'Privacy',terms:'Terms','medical-disclaimer':'Medical notice'},
 heroTitle:'A clearer path through medical travel coordination',
 heroLine:'Multilingual, nonclinical information about inquiries, appointment requests and travel arrangements. Licensed professionals make clinical decisions; staff must verify every real service.',
 start:'Explore the process',learn:'Our coordination services',badge:'Human coordination — no automatic bookings',
 intro:'Clear information, human review and meaningful consent. No medical guarantees or automatic partner endorsements.',
 heroStat1:'Five primary languages',heroStat2:'Human review required',
 stepsTitle:'Administrative guidance, never medical advice',servicesTitle:'What can be coordinated',
 legalTitle:'Transparency and data protection',legalText:'Health documents and personal details are accepted only after consent and only through the secure patient portal. Do not send them by messaging apps or email.',
 language:'Language',missing:'This localized page has not yet been reviewed and published.',notVerified:'Informational content. Treatment outcomes are not guaranteed.',
 footer:'Administrative medical travel coordination; we are not a healthcare provider. For emergencies, contact local emergency services.',
 stepDescriptions:['Review general information','Verify identity and consent independently','Human review of an inquiry','Coordinate with independently approved providers']
 }
};
export function publicSiteOrigin(){
 const raw=process.env.PUBLIC_SITE_URL||'';
 try{const url=new URL(raw);return url.protocol==='https:'?url.origin:'';}catch{return '';}
}
export function publicApiBase(){
 const raw=process.env.INTERNAL_API_URL||process.env.API_INTERNAL_URL||
   process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
 return raw.replace(/\/$/,'');
}
async function response(path:string){
 try{return await fetch(publicApiBase()+'/api/v1'+path,{
  method:'GET',cache:'no-store',headers:{'Accept':'application/json'}
 });}catch{return null;}
}
export async function getManifest(tenant:string):Promise<PublicManifest|null>{
 if(!isTenant(tenant))return null;
 const r=await response('/public/'+encodeURIComponent(tenant)+'/site-manifest');
 if(!r?.ok)return null;
 return r.json() as Promise<PublicManifest>;
}
export async function getPage(tenant:string,locale:PublicLocale,slug:string):Promise<PublicPage|null>{
 if(!isTenant(tenant)||!isSlug(slug))return null;
 const r=await response('/public/'+encodeURIComponent(tenant)+'/pages/'+locale+'/'+encodeURIComponent(slug));
 if(!r?.ok)return null;
 return r.json() as Promise<PublicPage>;
}
export function hasPage(manifest:PublicManifest,slug:string,locale:PublicLocale){
 return Boolean(manifest.pages.find(x=>x.slug===slug)?.translations[locale]);
}
export function seoAllowed(manifest:PublicManifest){
 return manifest.search_indexing_allowed && Boolean(publicSiteOrigin());
}
