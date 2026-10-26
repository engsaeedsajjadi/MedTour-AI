// Section 22: server-only, published-only public website data.
export const PUBLIC_LOCALES=['fa','ar','en'] as const;
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
 return s==='fa'||s==='ar'||s==='en';
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
 start:'مراحل هماهنگی را ببینید',learn:'آشنایی با خدمات',badge:'پیش‌نمایش آزمایشی — بدون رزرو واقعی',
 intro:'فرایندی شفاف، انسانی و مبتنی بر رضایت آگاهانه؛ بدون وعده درمان یا نتایج قطعی.',
 heroStat1:'سه زبان اصلی',heroStat2:'بررسی انسانی الزامی',
 stepsTitle:'همراه مسیر، بدون ادعای پزشکی',servicesTitle:'حوزه‌های هماهنگی اداری',
 legalTitle:'شفافیت و حفاظت از اطلاعات',legalText:'قبل از انتقال مدارک پزشکی یا اطلاعات شخصی، باید هویت و رضایت به‌صورت مستقل بررسی شود. نسخه نمایشی پذیرای مدارک واقعی نیست.',
 language:'زبان',missing:'این محتوا هنوز برای این زبان تأیید و منتشر نشده است.',notVerified:'محتوای معرفی آزمایشی؛ فاقد تضمین درمان و تأیید شریک خارجی.',
 footer:'پلتفرم آزمایشی هماهنگی غیر درمانی. در فوریت‌ها به اورژانس محلی مراجعه کنید.',
 stepDescriptions:['آشنایی با اطلاعات عمومی','رضایت و احراز هویت مستقل','بررسی انسانی درخواست','هماهنگی با ارائه‌دهنده تأییدشده']
 },
 ar:{
 brand:'MedTour AI',tagline:'تنسيق مسؤول للسفر العلاجي',nav:{about:'من نحن',services:'الخدمات',process:'الخطوات',faq:'الأسئلة',contact:'التواصل',privacy:'الخصوصية',terms:'الشروط','medical-disclaimer':'تنبيه طبي'},
 heroTitle:'خطوات أوضح لتنسيق السفر العلاجي',
 heroLine:'معلومات عامة بلغات متعددة حول التنسيق الإداري والمواعيد والسفر. القرارات الطبية للأطباء المؤهلين حصراً؛ كل خدمة تحتاج مراجعة بشرية مستقلة.',
 start:'استعرض الخطوات',learn:'تعرّف على الخدمات',badge:'عرض تجريبي — دون حجوزات فعلية',
 intro:'تنسيق شفاف بموافقة واعية ومتابعة بشرية؛ بلا وعود أو ضمانات علاجية.',
 heroStat1:'ثلاث لغات رئيسية',heroStat2:'مراجعة بشرية إلزامية',
 stepsTitle:'مرافقة إدارية، دون ادعاء طبي',servicesTitle:'مجالات التنسيق الإداري',
 legalTitle:'الشفافية وخصوصية البيانات',legalText:'قبل نقل أي وثائق صحية أو بيانات شخصية يجب التحقق المستقل من الهوية والموافقة. لا تقبل هذه النسخة بيانات مرضى حقيقية.',
 language:'اللغة',missing:'هذه الصفحة لم تتم مراجعتها ونشرها بهذه اللغة.',notVerified:'محتوى تعريفي تجريبي لا يضمن نتائج العلاج ولا اعتماد مقدمي الخدمات.',
 footer:'منصة تجريبية للتنسيق غير الطبي. للحالات العاجلة اتصل بخدمات الطوارئ المحلية.',
 stepDescriptions:['معلومات عامة','تحقق مستقل من الهوية والموافقة','مراجعة بشرية للطلب','تنسيق مع شريك معتمد']
 },
 en:{
 brand:'MedTour AI',tagline:'Responsible medical travel coordination',nav:{about:'About',services:'Services',process:'Process',faq:'FAQ',contact:'Contact',privacy:'Privacy',terms:'Terms','medical-disclaimer':'Medical notice'},
 heroTitle:'A clearer path through medical travel coordination',
 heroLine:'Multilingual, nonclinical information about inquiries, appointment requests and travel arrangements. Licensed professionals make clinical decisions; staff must verify every real service.',
 start:'Explore the process',learn:'Our coordination services',badge:'Alpha demonstration — no live reservations',
 intro:'Clear information, human review and meaningful consent. No medical guarantees or automatic partner endorsements.',
 heroStat1:'Three primary languages',heroStat2:'Human review required',
 stepsTitle:'Administrative guidance, never medical advice',servicesTitle:'What can be coordinated',
 legalTitle:'Transparency and data protection',legalText:'Identity and consent require independent verification before transmitting personal or health documents. This alpha environment cannot accept real patient information.',
 language:'Language',missing:'This localized page has not yet been reviewed and published.',notVerified:'Informational alpha content. No treatment guarantees or independently verified partners.',
 footer:'Nonclinical demonstration platform. For emergencies, contact local emergency services.',
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
