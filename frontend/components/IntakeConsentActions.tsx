'use client';
import {useState} from 'react';
import {request,Row} from '@/lib/api';

type ConsentPurpose='intake'|'communication';
type IssuedConsent={token:string;purpose:string;expires_in_seconds:number};
type PortalInvitation={token:string;demo_verification_code:string;expires_in_seconds:number};

export default function IntakeConsentActions({patients}:{patients:Row[]}) {
 const [selectedId,setSelectedId]=useState('');
 const [purpose,setPurpose]=useState<ConsentPurpose>('communication');
 const [consentLink,setConsentLink]=useState('');
 const [portalLink,setPortalLink]=useState('');
 const [demoCode,setDemoCode]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const currentId=patients.some(p=>p.id===selectedId)?selectedId:String(patients[0]?.id||'');

 function clearLinks(){setConsentLink('');setPortalLink('');setDemoCode('');setError('');setNotice('');}

 async function issueConsent(){
  if(!currentId)return;
  setBusy(true);setError('');setNotice('');setConsentLink('');
  try {
   const data=await request<IssuedConsent>('/consent-links/'+encodeURIComponent(currentId)+'/'+purpose,{method:'POST'});
   if(!data.token||data.purpose!==purpose)throw new Error('پاسخ صدور لینک رضایت نامعتبر است.');
   // The one-use token remains in local React memory; never print or persist it.
   setConsentLink(window.location.origin+'/consent#token='+encodeURIComponent(data.token));
   setNotice('لینک یک‌بارمصرف رضایت آزمایشی ۳۰ دقیقه اعتبار دارد. صدور لینک به معنی پذیرش رضایت نیست.');
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 async function issuePortal(){
  if(!currentId)return;
  setBusy(true);setError('');setNotice('');setPortalLink('');setDemoCode('');
  try {
   const data=await request<PortalInvitation>('/portal/invites/'+encodeURIComponent(currentId),{method:'POST'});
   if(!data.token||!/^[0-9]{6}$/.test(data.demo_verification_code))throw new Error('پاسخ دعوت آزمایشی نامعتبر است.');
   // This development-only manual OTP is not an independent identity factor.
   // Retain both challenge values in component memory, not logs, URLs (OTP), or storage.
   setPortalLink(window.location.origin+'/patient-portal#invite='+encodeURIComponent(data.token));
   setDemoCode(data.demo_verification_code);
   setNotice('دعوت آزمایشی ۱۰ دقیقه اعتبار دارد و با دعوت جدید باطل می‌شود؛ فقط برای بیمار ساختگی استفاده کنید.');
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 async function copyLink(value:string){
  try{
   await navigator.clipboard.writeText(value);
   setNotice('لینک محرمانه آزمایشی کپی شد؛ در سرویس‌های عمومی منتشر نکنید.');
  }catch{setError('کپی خودکار ممکن نیست؛ لینک را انتخاب و به‌صورت دستی کپی کنید.');}
 }

 return <section className="panel" style={{marginTop:18,padding:20}}>
  <div className="panelHeader"><h2>رضایت و دسترسی آزمایشی بیمار</h2></div>
  <p>ابتدا برای بیمار آزمایشی رضایت‌های پذیرش و ارتباطات را در فرم جداگانه ثبت کنید؛ سپس می‌توانید دعوت‌نامه ورود به پرتال بسازید.</p>
  <div className="infoBanner">فقط داده ساختگی در محیط توسعه. لینک‌ها محرمانه و یک‌بارمصرف‌اند؛ کد شش‌رقمی صرفاً برای تست دستی است و هویت واقعی بیمار را احراز نمی‌کند.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<p className="infoBanner" role="status">{notice}</p>}
  <div className="formGrid" style={{marginTop:12}}>
   <label>انتخاب بیمار آزمایشی
    <select aria-label="بیمار برای دسترسی آزمایشی" disabled={!patients.length||busy}
     value={currentId} onChange={e=>{setSelectedId(e.target.value);clearLinks();}}>
     {patients.length===0?<option value="">ابتدا بیمار آزمایشی ثبت کنید</option>:
      patients.map(p=><option key={String(p.id)} value={String(p.id)}>{String(p.full_name||'بیمار')} — {String(p.id).slice(0,8)}…</option>)}
    </select>
   </label>
   <label>نوع رضایت
    <select aria-label="نوع رضایت" value={purpose} disabled={busy}
     onChange={e=>{setPurpose(e.target.value as ConsentPurpose);setConsentLink('');setError('');setNotice('');}}>
     <option value="intake">پذیرش اولیه (intake)</option>
     <option value="communication">ارتباطات بیمار (communication)</option>
    </select>
   </label>
   <div className="formActions">
    <button className="button" type="button" disabled={!currentId||busy} onClick={issueConsent}>
     {busy?'در حال صدور…':'ایجاد لینک رضایت'}
    </button>
   </div>
  </div>
  {consentLink&&<div style={{display:'grid',gap:12,marginTop:14}}>
   <label>لینک محرمانه رضایت (۳۰ دقیقه اعتبار)
    <input aria-label="لینک رضایت آزمایشی" readOnly dir="ltr" value={consentLink} onFocus={e=>e.currentTarget.select()}/>
   </label>
   <div style={{display:'flex',flexWrap:'wrap',gap:10}}>
    <button type="button" className="button secondary" onClick={()=>copyLink(consentLink)}>کپی لینک</button>
    <a className="button" href={consentLink} target="_blank" rel="noopener noreferrer">بازکردن فرم رضایت آزمایشی</a>
   </div>
   <p>برای ثبت رضایت، در صفحه بازشده گزینه موافقت را به‌عنوان بیمار ساختگی انتخاب کنید.</p>
  </div>}
  <section style={{borderTop:'1px solid #cdd7df',marginTop:18,paddingTop:18}}>
   <h3>دعوت‌نامه پرتال بیمار آزمایشی</h3>
   <p>پس از ثبت هر دو رضایت intake و communication، دعوت‌نامه و کد شش‌رقمی را برای تست محلی صادر کنید.</p>
   <button className="button secondary" type="button" disabled={!currentId||busy} onClick={issuePortal}>
    {busy?'در حال صدور…':'ایجاد دعوت‌نامه پرتال'}
   </button>
   {portalLink&&demoCode&&<div style={{display:'grid',gap:12,marginTop:14}}>
    <label>لینک محرمانه دعوت (۱۰ دقیقه اعتبار)
     <input aria-label="لینک دعوت پرتال آزمایشی" dir="ltr" readOnly value={portalLink} onFocus={e=>e.currentTarget.select()}/>
    </label>
    <label>کد شش‌رقمی برای ورود آزمایشی
     <input aria-label="کد آزمایشی ورود پرتال" dir="ltr" readOnly value={demoCode} onFocus={e=>e.currentTarget.select()} />
    </label>
    <div style={{display:'flex',flexWrap:'wrap',gap:10}}>
     <button type="button" className="button secondary" onClick={()=>copyLink(portalLink)}>کپی لینک دعوت</button>
     <a className="button" href={portalLink} target="_blank" rel="noopener noreferrer">بازکردن پرتال بیمار آزمایشی</a>
    </div>
    <p>کد را جداگانه در فرم پرتال وارد کنید. پس از ورود موفق، دعوت و کد دیگر قابل استفاده نیستند.</p>
   </div>}
  </section>
 </section>;
}
