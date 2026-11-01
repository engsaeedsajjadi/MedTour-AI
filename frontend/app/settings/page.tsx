'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {cell} from '@/lib/i18n';
import {CURRENCIES,LANGUAGE_NAMES,TIMEZONES,loadOrganization,loadProfile,rememberOrganization,rememberTimezone,
 type Integrations,type Organization,type Profile} from '@/lib/preferences';

const TELEGRAM:Record<string,string>={off:'خاموش',polling_test:'فعال (حالت آزمایشی محلی)',webhook:'فعال (webhook روی سرور)'};
const CODE:Record<string,string>={email:'ایمیل',sms_webhook:'پیامک',not_configured:'تنظیم نشده'};
const STORAGE:Record<string,string>={object_storage_scanned:'فعال، با اسکن ویروس و رمزنگاری',not_configured:'تنظیم نشده'};

function Status({ok,children}:{ok:boolean,children:React.ReactNode}){
 return <span className={'badge '+(ok?'good':'warn')}>{children}</span>;
}

export default function SettingsPage(){
 const [tab,setTab]=useState<'me'|'org'>('me');
 const [profile,setProfile]=useState<Profile|null>(null),[name,setName]=useState(''),[zone,setZone]=useState('Asia/Tehran');
 const [org,setOrg]=useState<Organization|null>(null),[editable,setEditable]=useState(false),[integrations,setIntegrations]=useState<Integrations|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');

 async function reload(){
  const [p,o]=await Promise.all([loadProfile(),loadOrganization()]);
  setProfile(p);setName(p.display_name);setZone(p.timezone);
  setOrg(o.profile);setEditable(o.editable);setIntegrations(o.integrations||null);
 }
 useEffect(()=>{void reload().catch(e=>setError((e as Error).message));},[]);

 async function run(work:()=>Promise<void>,done:string){
  setBusy(true);setError('');setNotice('');
  try{await work();setNotice(done);}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 const saveProfile=(e:React.FormEvent)=>{e.preventDefault();void run(async()=>{
  const p=await request<Profile>('/account/profile',{method:'PUT',body:JSON.stringify({display_name:name,timezone:zone})});
  setProfile(p);rememberTimezone(p.timezone);window.dispatchEvent(new Event('medtour-settings'));
 },'تنظیمات حساب شما ذخیره شد.');};
 const signOutOthers=()=>void run(async()=>{
  const t=await request<{access_token:string;refresh_token:string}>('/account/sessions/sign-out-others',{method:'POST'});
  sessionStorage.setItem('medtour_token',t.access_token);sessionStorage.setItem('medtour_refresh',t.refresh_token);
  await reload();
 },'از همه دستگاه‌های دیگر خارج شدید. این مرورگر همچنان وارد است.');
 const saveOrg=(e:React.FormEvent)=>{e.preventDefault();if(!org)return;void run(async()=>{
  const v=await request<{profile:Organization;editable:boolean;integrations?:Integrations}>('/organization/profile',{method:'PUT',body:JSON.stringify(org)});
  setOrg(v.profile);rememberOrganization(v.profile);window.dispatchEvent(new Event('medtour-settings'));
 },'تنظیمات سازمان ذخیره و در پنل و پرتال بیمار اعمال شد.');};
 const set=<K extends keyof Organization>(k:K,v:Organization[K])=>setOrg(o=>o?{...o,[k]:v}:o);
 const toggleLang=(code:string)=>{if(!org)return;const has=org.enabled_languages.includes(code);
  const next=has?org.enabled_languages.filter(x=>x!==code):[...org.enabled_languages,code];
  set('enabled_languages',next);if(has&&org.default_language===code&&next.length)set('default_language',next[0]);};
 const zones=TIMEZONES.some(([z])=>z===zone)?TIMEZONES:[[zone,zone] as [string,string],...TIMEZONES];

 return <Shell title="تنظیمات">
  <div className="tabs" role="tablist">
   <button type="button" role="tab" aria-selected={tab==='me'} className={tab==='me'?'active':''} onClick={()=>setTab('me')}>حساب من</button>
   <button type="button" role="tab" aria-selected={tab==='org'} className={tab==='org'?'active':''} onClick={()=>setTab('org')}>سازمان</button>
  </div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}

  {tab==='me'&&profile&&<>
   <section className="panel"><div className="panelHeader"><h2>مشخصات من</h2><span className="subtle" dir="ltr">{profile.email}</span></div>
    <form className="formGrid" onSubmit={saveProfile}>
     <label>نام نمایشی (در بالای پنل نشان داده می‌شود)<input value={name} maxLength={80} onChange={e=>setName(e.target.value)} placeholder="مثلاً: سارا محمدی"/></label>
     <label>منطقه زمانی (برای نمایش همه تاریخ‌ها و ساعت‌ها)<select value={zone} onChange={e=>setZone(e.target.value)}>{zones.map(([z,label])=><option key={z} value={z}>{label}</option>)}</select></label>
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

  {tab==='org'&&org&&<>
   {!editable&&<div className="infoBanner">فقط مدیر سازمان می‌تواند این تنظیمات را تغییر دهد.</div>}
   <section className="panel"><div className="panelHeader"><h2>مشخصات و راه‌های تماس سازمان</h2><span className="subtle">در پنل و پرتال بیمار نمایش داده می‌شود</span></div>
    <form className="formGrid" onSubmit={saveOrg}>
     <fieldset disabled={!editable||busy} className="settingsFieldset">
      <label>نام سازمان<input required minLength={2} maxLength={120} value={org.display_name} onChange={e=>set('display_name',e.target.value)}/></label>
      <label>ایمیل پشتیبانی بیماران<input type="email" dir="ltr" value={org.contact_email} onChange={e=>set('contact_email',e.target.value)} placeholder="support@example.com"/></label>
      <label>تلفن پشتیبانی<input dir="ltr" value={org.contact_phone} onChange={e=>set('contact_phone',e.target.value)} placeholder="+98 21 ..."/></label>
      <label>ساعات پاسخ‌گویی<input value={org.patient_support_hours} onChange={e=>set('patient_support_hours',e.target.value)} placeholder="شنبه تا پنجشنبه، ۹ تا ۱۷"/></label>
      <label>وب‌سایت<input dir="ltr" value={org.website} onChange={e=>set('website',e.target.value)} placeholder="https://"/></label>
      <label>لینک اطلاعیه حریم خصوصی<input dir="ltr" value={org.privacy_notice_url} onChange={e=>set('privacy_notice_url',e.target.value)} placeholder="https://"/></label>
      <label>منطقه زمانی سازمان<select value={org.timezone} onChange={e=>set('timezone',e.target.value)}>{(TIMEZONES.some(([z])=>z===org.timezone)?TIMEZONES:[[org.timezone,org.timezone] as [string,string],...TIMEZONES]).map(([z,l])=><option key={z} value={z}>{l}</option>)}</select></label>
      <label>ارز پیش‌فرض پیش‌فاکتور<select value={org.default_currency} onChange={e=>set('default_currency',e.target.value)}>{CURRENCIES.map(c=><option key={c} value={c}>{c}</option>)}</select></label>
      <div className="settingsWide"><span className="fieldLabel">زبان‌های فعال برای بیماران</span>
       <div className="checkRow">{Object.entries(LANGUAGE_NAMES).map(([code,label])=><label key={code} className="checkItem"><input type="checkbox" checked={org.enabled_languages.includes(code)} onChange={()=>toggleLang(code)}/>{label}</label>)}</div></div>
      <label>زبان پیش‌فرض بیمار جدید<select value={org.default_language} onChange={e=>set('default_language',e.target.value)}>{org.enabled_languages.map(code=><option key={code} value={code}>{LANGUAGE_NAMES[code]}</option>)}</select></label>
      {editable&&<div className="formActions"><button className="button" disabled={busy||!org.enabled_languages.length}>ذخیره تنظیمات سازمان</button></div>}
     </fieldset>
    </form>
   </section>
   {integrations&&<section className="panel"><div className="panelHeader"><h2>وضعیت اتصال سرویس‌ها</h2><span className="subtle">فقط نمایش؛ روی سرور تنظیم می‌شود</span></div>
    <div className="settingsRows">
     <p>ربات تلگرام: <Status ok={integrations.telegram.mode!=='off'}>{TELEGRAM[integrations.telegram.mode]||integrations.telegram.mode}</Status> · لینک اپراتور: <Status ok={integrations.telegram.operator_link_configured}>{integrations.telegram.operator_link_configured?'تنظیم شده':'تنظیم نشده'}</Status></p>
     <p>ارسال کد ورود بیمار: <Status ok={integrations.patient_code_delivery!=='not_configured'}>{CODE[integrations.patient_code_delivery]||integrations.patient_code_delivery}</Status></p>
     <p>مخزن امن مدارک: <Status ok={integrations.secure_document_storage!=='not_configured'}>{STORAGE[integrations.secure_document_storage]||integrations.secure_document_storage}</Status></p>
     <p>ورود دومرحله‌ای کارکنان: <Status ok={integrations.staff_two_factor_required}>{integrations.staff_two_factor_required?'اجباری':'اختیاری'}</Status></p>
     <p className="subtle">رمز ایمیل، توکن ربات، لینک اپراتور ربات و کلیدهای رمزنگاری عمداً از پنل قابل تغییر نیستند تا با نفوذ به یک حساب مدیر لو نروند. این موارد را مسئول سرور در فایل <code>.env</code> تنظیم می‌کند.</p>
    </div>
   </section>}
  </>}
 </Shell>;
}
