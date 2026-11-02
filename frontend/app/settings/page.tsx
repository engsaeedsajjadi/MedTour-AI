'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {cell} from '@/lib/i18n';
import {allowedFor} from '@/lib/roles';
import {CURRENCIES,LANGUAGE_NAMES,MFA_ROLES,START_PAGES,TIMEZONES,loadOrganization,loadProfile,rememberDisplay,rememberOrganization,
 type Integrations,type Organization,type Profile} from '@/lib/preferences';

type Tab='me'|'org'|'ai'|'base';
type Agent={agent_key:string;allowed_workflows:string[];enabled:boolean;provider_mode:string;daily_run_limit:number};
const TELEGRAM:Record<string,string>={off:'خاموش',polling_test:'فعال (حالت محلی polling)',webhook:'فعال (webhook روی سرور)'};
const CODE:Record<string,string>={email:'ایمیل',sms_webhook:'پیامک',not_configured:'تنظیم نشده'};
const STORAGE:Record<string,string>={object_storage_scanned:'فعال، با اسکن ویروس و رمزنگاری',not_configured:'تنظیم نشده'};
const AGENT_INFO:Record<string,[string,string]>={
 administrative_receptionist:['منشی اداری','پاسخ به پرسش‌های عمومی، یادآوری عدم ارسال مدارک در پیام‌رسان و ارجاع به کارشناس'],
 travel_coordinator:['هماهنگ‌کننده سفر','پیش‌نویس توضیح مراحل سفر، نوبت و ویزا برای بیمار'],
 knowledge_assistant:['دستیار پایگاه دانش','پیدا کردن پاسخ استاندارد مناسب در پایگاه دانش سازمان'],
};
const MODES:[string,string][]=[['deterministic_demo','قالب ثابت (بدون مدل زبانی)'],['approved_provider','مدل زبانی ارائه‌دهنده تأییدشده']];
type Card={href:string;title:string;text:string;admin?:boolean};
const BASE:{group:string;cards:Card[]}[]=[
 {group:'مراکز درمانی و پزشکان',cards:[
  {href:'/hospitals',title:'بیمارستان‌ها',text:'فهرست مراکز درمانی همکار'},
  {href:'/hospital-management',title:'مدارک و ظرفیت بیمارستان‌ها',text:'مجوز، خدمات و ظرفیت هر مرکز',admin:true},
  {href:'/providers',title:'پزشکان',text:'فهرست پزشکان و تخصص‌ها'},
  {href:'/physician-management',title:'مدارک و برنامه پزشکان',text:'پروانه، همکاری با بیمارستان و ساعات کاری',admin:true}]},
 {group:'سفر و اقامت',cards:[
  {href:'/settings/hotels',title:'هتل‌ها و ظرفیت اتاق',text:'هتل‌های طرف قرارداد و اتاق‌های در اختیار',admin:true},
  {href:'/settings/transport',title:'خودروها و مترجمان',text:'ترانسفر فرودگاهی، مترجم و ساعات در دسترس',admin:true}]},
 {group:'مالی',cards:[
  {href:'/prices',title:'تعرفه خدمات',text:'قیمت مستند هر خدمت برای پیش‌فاکتور'},
  {href:'/settings/exchange-rates',title:'نرخ ارز',text:'نرخ تبدیل ارز با مرجع و تاریخ اعتبار',admin:true}]},
 {group:'کاربران و همکاران',cards:[
  {href:'/staff',title:'کاربران و نقش‌ها',text:'حساب کارکنان، نقش و فعال/غیرفعال',admin:true},
  {href:'/agents',title:'نمایندگان بین‌المللی',text:'نمایندگان، قرارداد و حساب پرتال',admin:true}]},
 {group:'محتوا',cards:[
  {href:'/cms',title:'محتوای وب‌سایت',text:'صفحات عمومی سایت به پنج زبان'},
  {href:'/knowledge',title:'پایگاه دانش',text:'پاسخ‌های استاندارد برای هماهنگ‌کنندگان و دستیارها'}]},
];

function Status({ok,children}:{ok:boolean,children:React.ReactNode}){
 return <span className={'badge '+(ok?'good':'warn')}>{children}</span>;
}
const lines=(v:string)=>v.split('\n').map(x=>x.trim()).filter(Boolean);

export default function SettingsPage(){
 const [tab,setTab]=useState<Tab>('me'),[role,setRole]=useState('');
 const [profile,setProfile]=useState<Profile|null>(null);
 const [me,setMe]=useState({display_name:'',timezone:'Asia/Tehran',calendar:'jalali',digits:'persian',start_page:''});
 const [org,setOrg]=useState<Organization|null>(null),[editable,setEditable]=useState(false),[owner,setOwner]=useState(false);
 const [integrations,setIntegrations]=useState<Integrations|null>(null);
 const [authorities,setAuthorities]=useState(''),[desks,setDesks]=useState('');
 const [agents,setAgents]=useState<Agent[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');

 useEffect(()=>{const t=new URLSearchParams(window.location.search).get('tab');if(t==='org'||t==='base'||t==='ai')setTab(t);},[]);
 async function reload(){
  const [p,o]=await Promise.all([loadProfile(),loadOrganization()]);
  setProfile(p);setRole(p.role);
  setMe({display_name:p.display_name,timezone:p.timezone,calendar:p.calendar,digits:p.digits,start_page:p.start_page});
  setOrg(o.profile);setEditable(o.editable);setOwner(!!o.telegram_bot_owner);setIntegrations(o.integrations||null);
  setAuthorities(o.profile.visa_authorities.join('\n'));setDesks(o.profile.supplier_desks.join('\n'));
  if(p.role==='admin'||p.role==='operator'){
   try{setAgents((await request<{agents:Agent[]}>('/ai-orchestration/catalog')).agents);}catch{setAgents([]);}
  }
 }
 useEffect(()=>{void reload().catch(e=>setError((e as Error).message));},[]);
 async function run(work:()=>Promise<void>,done:string){
  setBusy(true);setError('');setNotice('');
  try{await work();setNotice(done);}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 const saveProfile=(e:React.FormEvent)=>{e.preventDefault();void run(async()=>{
  const p=await request<Profile>('/account/profile',{method:'PUT',body:JSON.stringify(me)});
  setProfile(p);rememberDisplay(p);window.dispatchEvent(new Event('medtour-settings'));
 },'تنظیمات حساب شما ذخیره شد.');};
 const signOutOthers=()=>void run(async()=>{
  const t=await request<{access_token:string;refresh_token:string}>('/account/sessions/sign-out-others',{method:'POST'});
  sessionStorage.setItem('medtour_token',t.access_token);sessionStorage.setItem('medtour_refresh',t.refresh_token);
  await reload();
 },'از همه دستگاه‌های دیگر خارج شدید. این مرورگر همچنان وارد است.');
 const saveOrg=(e:React.FormEvent)=>{e.preventDefault();if(!org)return;void run(async()=>{
  const body={...org,visa_authorities:lines(authorities),supplier_desks:lines(desks)};
  const v=await request<{profile:Organization;telegram_bot_owner?:boolean;integrations?:Integrations}>('/organization/profile',{method:'PUT',body:JSON.stringify(body)});
  setOrg(v.profile);setAuthorities(v.profile.visa_authorities.join('\n'));setDesks(v.profile.supplier_desks.join('\n'));
  setIntegrations(v.integrations||null);rememberOrganization(v.profile);window.dispatchEvent(new Event('medtour-settings'));
 },'تنظیمات سازمان ذخیره و در پنل، پرتال بیمار، ربات و پیش‌فاکتورها اعمال شد.');};
 const saveAgent=(a:Agent)=>void run(async()=>{
  await request('/ai-orchestration/agents/'+a.agent_key,{method:'PUT',body:JSON.stringify({enabled:a.enabled,provider_mode:a.provider_mode,daily_run_limit:a.daily_run_limit})});
  setAgents((await request<{agents:Agent[]}>('/ai-orchestration/catalog')).agents);
 },'تنظیمات «'+(AGENT_INFO[a.agent_key]?.[0]||a.agent_key)+'» ذخیره شد.');
 const editAgent=(key:string,patch:Partial<Agent>)=>setAgents(xs=>xs.map(x=>x.agent_key===key?{...x,...patch}:x));
 const set=<K extends keyof Organization>(k:K,v:Organization[K])=>setOrg(o=>o?{...o,[k]:v}:o);
 const toggleLang=(code:string)=>{if(!org)return;const has=org.enabled_languages.includes(code);
  const next=has?org.enabled_languages.filter(x=>x!==code):[...org.enabled_languages,code];
  set('enabled_languages',next);if(has&&org.default_language===code&&next.length)set('default_language',next[0]);};
 const toggleRole=(r:string)=>{if(!org)return;set('two_factor_roles',org.two_factor_roles.includes(r)?org.two_factor_roles.filter(x=>x!==r):[...org.two_factor_roles,r]);};
 const zoneOptions=(z:string)=>TIMEZONES.some(([x])=>x===z)?TIMEZONES:[[z,z] as [string,string],...TIMEZONES];
 const staffRole=role==='admin'||role==='operator';
 const ai=integrations?.ai;

 return <Shell title="تنظیمات">
  <div className="tabs" role="tablist">
   {([['me','حساب من'],['org','سازمان'],...(staffRole?[['ai','هوش مصنوعی'],['base','اطلاعات پایه']]:[])] as [Tab,string][]).map(([k,l])=>
    <button key={k} type="button" role="tab" aria-selected={tab===k} className={tab===k?'active':''} onClick={()=>setTab(k)}>{l}</button>)}
  </div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}

  {tab==='me'&&profile&&<>
   <section className="panel"><div className="panelHeader"><h2>مشخصات و نمایش</h2><span className="subtle" dir="ltr">{profile.email}</span></div>
    <form className="formGrid" onSubmit={saveProfile}>
     <label>نام نمایشی (در بالای پنل نشان داده می‌شود)<input value={me.display_name} maxLength={80} onChange={e=>setMe({...me,display_name:e.target.value})} placeholder="مثلاً: سارا محمدی"/></label>
     <label>منطقه زمانی<select value={me.timezone} onChange={e=>setMe({...me,timezone:e.target.value})}>{zoneOptions(me.timezone).map(([z,l])=><option key={z} value={z}>{l}</option>)}</select></label>
     <label>تقویم<select value={me.calendar} onChange={e=>setMe({...me,calendar:e.target.value})}><option value="jalali">هجری شمسی</option><option value="gregorian">میلادی</option></select></label>
     <label>ارقام<select value={me.digits} onChange={e=>setMe({...me,digits:e.target.value})}><option value="persian">فارسی (۱۲۳)</option><option value="latin">لاتین (123)</option></select></label>
     <label>صفحه شروع پس از ورود<select value={me.start_page} onChange={e=>setMe({...me,start_page:e.target.value})}>
      {START_PAGES.filter(([p])=>!p||allowedFor(role,p)).map(([p,l])=><option key={p||'default'} value={p}>{l}</option>)}</select></label>
     <div className="formActions"><button className="button" disabled={busy}>ذخیره</button></div>
    </form>
   </section>
   <section className="panel"><div className="panelHeader"><h2>امنیت ورود</h2></div>
    <div className="settingsRows">
     <p>ورود دومرحله‌ای: <Status ok={profile.two_factor_enabled}>{profile.two_factor_enabled?'فعال':'غیرفعال'}</Status>{profile.two_factor_required&&<span className="subtle"> · برای نقش شما اجباری است</span>}</p>
     <p><Link className="button secondary" href="/account-security">تغییر رمز عبور و مدیریت ورود دومرحله‌ای</Link></p>
    </div>
   </section>
   <section className="panel"><div className="panelHeader"><h2>دستگاه‌های واردشده</h2>
    <button type="button" className="button secondary" disabled={busy||profile.sessions.length<2} onClick={signOutOthers}>خروج از همه دستگاه‌های دیگر</button></div>
    <div className="tableScroll"><table><thead><tr><th>شروع</th><th>آخرین استفاده</th><th>اعتبار تا</th><th>ورود دومرحله‌ای</th></tr></thead><tbody>
     {profile.sessions.length===0?<tr><td className="empty" colSpan={4}>نشست فعالی ثبت نشده است.</td></tr>:profile.sessions.map((s,i)=><tr key={i}>
      <td>{cell('started_at',s.started_at)}</td><td>{cell('last_used_at',s.last_used_at)}</td><td>{cell('expires_at',s.expires_at)}</td><td>{s.two_factor?'بله':'خیر'}</td></tr>)}
    </tbody></table></div>
    <p className="subtle settingsNote">اگر دستگاهی را نمی‌شناسید، «خروج از همه دستگاه‌های دیگر» را بزنید و رمز عبور خود را عوض کنید.</p>
   </section>
  </>}

  {tab==='org'&&org&&<form onSubmit={saveOrg}>
   {!editable&&<div className="infoBanner">فقط مدیر سازمان می‌تواند این تنظیمات را تغییر دهد.</div>}
   <fieldset disabled={!editable||busy} className="settingsFieldsetBlock">
    <section className="panel"><div className="panelHeader"><h2>مشخصات و راه‌های تماس</h2><span className="subtle">در پنل و پرتال بیمار نمایش داده می‌شود</span></div>
     <div className="formGrid">
      <label>نام سازمان<input required minLength={2} maxLength={120} value={org.display_name} onChange={e=>set('display_name',e.target.value)}/></label>
      <label>نام لاتین سازمان (برای PDF پیش‌فاکتور)<input dir="ltr" maxLength={100} value={org.latin_name} onChange={e=>set('latin_name',e.target.value)} placeholder="Example Health Travel Co."/></label>
      <label>ایمیل پشتیبانی بیماران<input type="email" dir="ltr" value={org.contact_email} onChange={e=>set('contact_email',e.target.value)} placeholder="support@example.com"/></label>
      <label>تلفن پشتیبانی<input dir="ltr" value={org.contact_phone} onChange={e=>set('contact_phone',e.target.value)} placeholder="+98 21 ..."/></label>
      <label>ساعات پاسخ‌گویی<input value={org.patient_support_hours} onChange={e=>set('patient_support_hours',e.target.value)} placeholder="شنبه تا پنجشنبه، ۹ تا ۱۷"/></label>
      <label>وب‌سایت<input dir="ltr" value={org.website} onChange={e=>set('website',e.target.value)} placeholder="https://"/></label>
      <label>منطقه زمانی سازمان<select value={org.timezone} onChange={e=>set('timezone',e.target.value)}>{zoneOptions(org.timezone).map(([z,l])=><option key={z} value={z}>{l}</option>)}</select></label>
     </div>
    </section>
    <section className="panel"><div className="panelHeader"><h2>بیماران و حریم خصوصی</h2></div>
     <div className="formGrid">
      <div className="settingsWide"><span className="fieldLabel">زبان‌های فعال برای بیماران</span>
       <div className="checkRow">{Object.entries(LANGUAGE_NAMES).map(([code,label])=><label key={code} className="checkItem"><input type="checkbox" checked={org.enabled_languages.includes(code)} onChange={()=>toggleLang(code)}/>{label}</label>)}</div></div>
      <label>زبان پیش‌فرض بیمار جدید<select value={org.default_language} onChange={e=>set('default_language',e.target.value)}>{org.enabled_languages.map(code=><option key={code} value={code}>{LANGUAGE_NAMES[code]}</option>)}</select></label>
      <label>لینک اطلاعیه حریم خصوصی<input dir="ltr" value={org.privacy_notice_url} onChange={e=>set('privacy_notice_url',e.target.value)} placeholder="https://"/></label>
      <label>نسخه اطلاعیه حریم خصوصی (با هر رضایت ثبت می‌شود)<input dir="ltr" required maxLength={40} pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,39}" value={org.privacy_notice_version} onChange={e=>set('privacy_notice_version',e.target.value)} placeholder="2026-11"/></label>
     </div>
    </section>
    <section className="panel"><div className="panelHeader"><h2>پیش‌فاکتور</h2></div>
     <div className="formGrid">
      <label>ارز پیش‌فرض<select value={org.default_currency} onChange={e=>set('default_currency',e.target.value)}>{CURRENCIES.map(c=><option key={c} value={c}>{c}</option>)}</select></label>
      <label>مدت اعتبار پیش‌فاکتور (روز)<input type="number" min={1} max={180} value={org.quote_validity_days} onChange={e=>set('quote_validity_days',Number(e.target.value))}/></label>
      <label className="settingsWide">یادداشت پایین PDF (لاتین، اختیاری)<input dir="ltr" maxLength={200} value={org.quote_footer_note} onChange={e=>set('quote_footer_note',e.target.value)} placeholder="Prices include hospital fees; flights are not included."/></label>
     </div>
    </section>
    <section className="panel"><div className="panelHeader"><h2>فهرست‌های آماده</h2><span className="subtle">هر مورد در یک خط، با حروف لاتین؛ در صفحات ویزا، هتل و ترانسفر از این فهرست انتخاب می‌شود</span></div>
     <div className="formGrid">
      <label>مراجع ویزا (سفارت‌ها و کنسولگری‌ها)<textarea dir="ltr" rows={5} value={authorities} onChange={e=>setAuthorities(e.target.value)} placeholder={'Iran Embassy Kabul\nIran Consulate Herat'}/></label>
      <label>واحدهای ارائه‌دهنده (رزرو هتل، شرکت ترانسفر)<textarea dir="ltr" rows={5} value={desks} onChange={e=>setDesks(e.target.value)} placeholder={'Azadi Hotel Reservations\nCity Transfer Dispatch'}/></label>
     </div>
    </section>
    <section className="panel"><div className="panelHeader"><h2>ربات تلگرام</h2></div>
     <div className="formGrid">
      <label className="settingsWide">لینک دکمه «تماس با اپراتور»{!owner&&<span className="subtle"> (ربات این سرور متعلق به سازمان دیگری است)</span>}<input dir="ltr" disabled={!owner} value={org.telegram_operator_url} onChange={e=>set('telegram_operator_url',e.target.value)} placeholder="https://t.me/operator_username"/></label>
     </div>
    </section>
    <section className="panel"><div className="panelHeader"><h2>امنیت</h2></div>
     <div className="formGrid">
      <div className="settingsWide"><span className="fieldLabel">نقش‌هایی که ورود دومرحله‌ای برایشان اجباری است</span>
       <div className="checkRow">{MFA_ROLES.map(([r,l])=><label key={r} className="checkItem"><input type="checkbox" checked={org.two_factor_roles.includes(r)} onChange={()=>toggleRole(r)}/>{l}</label>)}</div>
       <span className="subtle">اگر سرور ورود دومرحله‌ای را برای مدیر و اپراتور اجباری کرده باشد، با برداشتن تیک هم اختیاری نمی‌شود.</span></div>
     </div>
    </section>
    {editable&&<p><button className="button" disabled={busy||!org.enabled_languages.length}>ذخیره تنظیمات سازمان</button></p>}
   </fieldset>
   {integrations&&<section className="panel"><div className="panelHeader"><h2>وضعیت اتصال سرویس‌ها</h2><span className="subtle">فقط نمایش؛ روی سرور تنظیم می‌شود</span></div>
    <div className="settingsRows">
     <p>ربات تلگرام: <Status ok={integrations.telegram.mode!=='off'}>{TELEGRAM[integrations.telegram.mode]||integrations.telegram.mode}</Status> · لینک اپراتور: <Status ok={integrations.telegram.operator_link_configured}>{integrations.telegram.operator_link_configured?'تنظیم شده':'تنظیم نشده'}</Status></p>
     <p>ارسال کد ورود بیمار: <Status ok={integrations.patient_code_delivery!=='not_configured'}>{CODE[integrations.patient_code_delivery]||integrations.patient_code_delivery}</Status></p>
     <p>مخزن امن مدارک: <Status ok={integrations.secure_document_storage!=='not_configured'}>{STORAGE[integrations.secure_document_storage]||integrations.secure_document_storage}</Status></p>
     <p>ورود دومرحله‌ای کارکنان (سرور): <Status ok={integrations.staff_two_factor_required}>{integrations.staff_two_factor_required?'اجباری':'اختیاری'}</Status></p>
     <p>ارسال پیام واتس‌اپ: <Status ok={integrations.whatsapp_outbound_approved}>{integrations.whatsapp_outbound_approved?'فعال':'غیرفعال'}</Status> · پردازش پیام صوتی: <Status ok={integrations.voice_processing_approved}>{integrations.voice_processing_approved?'فعال':'غیرفعال'}</Status></p>
     <p className="subtle">رمز ایمیل و پیامک، توکن ربات، کلید هوش مصنوعی و کلیدهای رمزنگاری عمداً از پنل قابل تغییر نیستند تا با نفوذ به یک حساب مدیر لو نروند. این موارد را مسئول سرور در فایل <code>.env</code> تنظیم می‌کند.</p>
    </div>
   </section>}
  </form>}

  {tab==='ai'&&staffRole&&<>
   <section className="panel"><div className="panelHeader"><h2>اتصال مدل زبانی</h2><span className="subtle">روی سرور تنظیم می‌شود</span></div>
    {ai?<div className="settingsRows">
     <p>وضعیت: <Status ok={ai.provider_ready}>{ai.provider_ready?'متصل و آماده':'آماده نیست'}</Status></p>
     <p>مدل: <code>{ai.model||'تنظیم نشده'}</code> · سرویس‌دهنده: <code>{ai.host||'تنظیم نشده'}</code> · کلید API: <Status ok={ai.key_configured}>{ai.key_configured?'تنظیم شده':'تنظیم نشده'}</Status> · تأیید قرارداد: <Status ok={ai.provider_approved}>{ai.provider_approved?'ثبت شده':'ثبت نشده'}</Status></p>
     {!ai.assistants_allowed_in_this_environment&&<p className="errorBox">در محیط عملیاتی، دستیارها تا تأیید رسمی پردازش داده توسط ارائه‌دهنده هوش مصنوعی خاموش می‌مانند.</p>}
     <p className="subtle">برای اتصال، مسئول سرور مقادیر <code>AI_BASE_URL</code>، <code>AI_MODEL</code>، <code>AI_API_KEY</code>، <code>AI_APPROVED_HOSTS</code> و پس از عقد قرارداد پردازش داده <code>AI_PROVIDER_APPROVED=true</code> را در <code>.env</code> وارد می‌کند. بدون اتصال، دستیارها فقط با «قالب ثابت» کار می‌کنند.</p>
    </div>:<div className="settingsRows"><p className="subtle">وضعیت اتصال فقط برای مدیر نمایش داده می‌شود.</p></div>}
   </section>
   <section className="panel"><div className="panelHeader"><h2>دستیارها</h2><span className="subtle">هیچ دستیاری پیام خودکار نمی‌فرستد؛ هر خروجی را کارشناس تأیید می‌کند</span></div>
    <div className="tableScroll"><table><thead><tr><th>دستیار</th><th>کار</th><th>فعال</th><th>حالت کار</th><th>سقف اجرای روزانه</th><th></th></tr></thead><tbody>
     {agents.length===0?<tr><td className="empty" colSpan={6}>دستیاری در دسترس نیست.</td></tr>:agents.map(a=><tr key={a.agent_key}>
      <td><strong>{AGENT_INFO[a.agent_key]?.[0]||a.agent_key}</strong></td>
      <td className="wrapCell">{AGENT_INFO[a.agent_key]?.[1]||a.allowed_workflows.join('، ')}</td>
      <td><input type="checkbox" aria-label="فعال" disabled={role!=='admin'} checked={a.enabled} onChange={e=>editAgent(a.agent_key,{enabled:e.target.checked})}/></td>
      <td><select disabled={role!=='admin'} value={a.provider_mode} onChange={e=>editAgent(a.agent_key,{provider_mode:e.target.value})}>
       {MODES.map(([k,l])=><option key={k} value={k} disabled={k==='approved_provider'&&!!ai&&!ai.provider_ready}>{l}</option>)}</select></td>
      <td><input type="number" min={1} max={100} disabled={role!=='admin'} value={a.daily_run_limit} onChange={e=>editAgent(a.agent_key,{daily_run_limit:Number(e.target.value)})} style={{width:80}}/></td>
      <td>{role==='admin'&&<button type="button" className="button secondary" disabled={busy} onClick={()=>saveAgent(a)}>ذخیره</button>}</td>
     </tr>)}
    </tbody></table></div>
    <p className="subtle settingsNote">اجرای دستیارها و بازبینی خروجی‌ها در صفحه <Link className="textLink" href="/ai-orchestration">دستیارهای هوشمند</Link> انجام می‌شود. پاسخ‌های استاندارد را در <Link className="textLink" href="/knowledge">پایگاه دانش</Link> تعریف کنید.</p>
   </section>
  </>}

  {tab==='base'&&staffRole&&<>
   <div className="infoBanner">اطلاعاتی که یک بار تعریف می‌شوند و در کار روزانه از آن‌ها انتخاب می‌کنید. موارد «فقط مدیر» را فقط مدیر سازمان می‌تواند تغییر دهد.</div>
   {BASE.map(g=><section key={g.group} className="panel"><div className="panelHeader"><h2>{g.group}</h2></div>
    <div className="settingsCards">{g.cards.filter(c=>role==='admin'||!c.admin).map(c=><Link key={c.href} href={c.href} className="settingsCard">
     <strong>{c.title}</strong><span>{c.text}</span>{c.admin&&<small>فقط مدیر</small>}</Link>)}</div>
   </section>)}
  </>}
 </Shell>;
}
