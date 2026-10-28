'use client';
import {useState} from 'react';
import {request,Row} from '@/lib/api';

type IssuedConsent={token:string;purpose:string;expires_in_seconds:number};

export default function IntakeConsentActions({patients}:{patients:Row[]}) {
 const [selectedId,setSelectedId]=useState('');
 const [link,setLink]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const currentId=patients.some(p=>p.id===selectedId)?selectedId:String(patients[0]?.id||'');

 async function issue() {
  if(!currentId)return;
  setBusy(true);setError('');setNotice('');setLink('');
  try {
   const data=await request<IssuedConsent>('/consent-links/'+encodeURIComponent(currentId)+'/intake',{method:'POST'});
   if(!data.token||data.purpose!=='intake')throw new Error('پاسخ صدور لینک رضایت نامعتبر است.');
   // Telegram, email or patient records must NOT contain the token in this development flow.
   // Keep the one-time token in local component memory; never put it in analytics/logs.
   setLink(window.location.origin+'/consent#token='+encodeURIComponent(data.token));
   setNotice('لینک یک‌بارمصرف آزمایشی تا ۳۰ دقیقه اعتبار دارد.');
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 async function copyLink(){
  try {
   await navigator.clipboard.writeText(link);
   setNotice('لینک آزمایشی کپی شد؛ فقط در محیط توسعه استفاده کنید.');
  }catch{
   setError('کپی خودکار ممکن نیست؛ لینک را از کادر انتخاب و کپی کنید.');
  }
 }

 return <section className="panel" style={{marginTop:18,padding:20}}>
  <div className="panelHeader"><h2>رضایت پذیرش بیمار آزمایشی</h2></div>
  <p>پیش از تشکیل پرونده، لینک اختصاصی `intake` را صادر کنید و فقط برای شبیه‌سازی، در مرورگر به‌عنوان بیمار آزمایشی آن را تأیید کنید. صدور لینک توسط مدیر به‌معنی ثبت رضایت نیست.</p>
  <div className="infoBanner">فقط داده ساختگی. لینک دسترسی محرمانه و یک‌بارمصرف است؛ دریافت آن احراز هویت پزشکی محسوب نمی‌شود. برای بیماران واقعی استفاده نکنید.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<p className="infoBanner" role="status">{notice}</p>}
  <div className="formGrid" style={{marginTop:12}}>
   <label>انتخاب بیمار آزمایشی
    <select aria-label="بیمار برای صدور لینک رضایت" disabled={!patients.length||busy}
     value={currentId} onChange={e=>{setSelectedId(e.target.value);setLink('');setError('');setNotice('');}}>
     {patients.length===0?<option value="">ابتدا بیمار آزمایشی ثبت کنید</option>:
      patients.map(p=><option key={String(p.id)} value={String(p.id)}>{String(p.full_name||'بیمار')} — {String(p.id).slice(0,8)}…</option>)}
    </select>
   </label>
   <div className="formActions">
    <button className="button" type="button" disabled={!currentId||busy} onClick={issue}>
     {busy?'در حال صدور…':'ایجاد لینک رضایت پذیرش'}
    </button>
   </div>
  </div>
  {link&&<div style={{display:'grid',gap:12,marginTop:14}}>
   <label>لینک محرمانه آزمایشی (تا ۳۰ دقیقه معتبر)
    <input aria-label="لینک رضایت آزمایشی" readOnly dir="ltr" value={link} onFocus={e=>e.currentTarget.select()}/>
   </label>
   <div style={{display:'flex',flexWrap:'wrap',gap:10}}>
    <button type="button" className="button secondary" onClick={copyLink}>کپی لینک</button>
    <a className="button" href={link} target="_blank" rel="noopener noreferrer">بازکردن فرم رضایت آزمایشی</a>
   </div>
   <p>بعد از پذیرش رضایت در صفحه جدید، از بخش «پرونده‌ها» برای همین بیمار پرونده بسازید.</p>
  </div>}
 </section>;
}
