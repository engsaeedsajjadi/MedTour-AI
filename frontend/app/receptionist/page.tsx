'use client';

import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {useEffect,useState} from 'react';

type Language={code:string;name:string;direction:'ltr'|'rtl';copy_reviewed_by_native_speaker:boolean};
type Intent='greeting'|'appointment'|'quote'|'documents'|'visa'|'human'|'general';
type Catalog={
 production_ready:boolean;speech_enabled:boolean;clinical_translation_validated:boolean;
 supported_languages:Language[];intents:Intent[];
};
type Preview={language:string;intent:Intent;message:string;human_review_required:boolean;external_message_sent:boolean};
const labels:Record<Intent,string>={
 greeting:'خوشامدگویی',appointment:'نوبت‌دهی',quote:'هزینه و پیش‌فاکتور',
 documents:'مدارک',visa:'ویزا و سفر',human:'درخواست اپراتور',general:'پاسخ عمومی'
};

export default function Receptionist(){
 const [catalog,setCatalog]=useState<Catalog|null>(null);
 const [locale,setLocale]=useState('fa');
 const [intent,setIntent]=useState<Intent>('greeting');
 const [preview,setPreview]=useState<Preview|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 useEffect(()=>{
   request<Catalog>('/receptionist/catalog').then(setCatalog).catch(e=>setError((e as Error).message));
 },[]);
 async function show(e:React.FormEvent){
   e.preventDefault();setBusy(true);setError('');setPreview(null);
   try{
     setPreview(await request<Preview>('/receptionist/preview',{
       method:'POST',body:JSON.stringify({language:locale,intent})
     }));
   }catch(e){setError((e as Error).message);}
   finally{setBusy(false);}
 }
 const direction=catalog?.supported_languages.find(x=>x.code===preview?.language)?.direction||'rtl';
 return <Shell title="منشی هوشمند چندزبانه">
  <div className="infoBanner">
   این صفحه صرفاً پیش‌نمایش متن‌های هماهنگی اداری است. هیچ پیام بیمار یا اطلاعات پزشکی دریافت نمی‌کند و هیچ ارتباط خارجی برقرار نمی‌سازد. کیفیت ترجمه بالینی و پاسخ صوتی تأیید نشده است.
  </div>
  {error&&<p className="errorBox" role="alert">{error}</p>}
  <section className="panel" style={{padding:22}}>
   <h2>پوشش زبان و ایمنی</h2>
   {!catalog?<p>در حال بررسی قابلیت‌ها...</p>:<>
    <div style={{display:'flex',gap:10,flexWrap:'wrap',margin:'12px 0'}}>
     {catalog.supported_languages.map(lang=><span className="badge" key={lang.code}>{lang.name} ({lang.code}) · {lang.direction.toUpperCase()}</span>)}
    </div>
    <p>نسخه عملیاتی: {catalog.production_ready?'آماده':'غیرفعال'} | صوت: {catalog.speech_enabled?'فعال':'تحویل‌نشده'} | تأیید ترجمه پزشکی: {catalog.clinical_translation_validated?'ثبت‌شده':'ثبت‌نشده'}</p>
    <p>پیش از استفاده واقعی، تمام متن‌های هر پنج زبان باید توسط بازبین بومی‌زبان و مسئول ایمنی پزشکی بررسی شوند.</p>
    <form onSubmit={show} className="formGrid">
     <label>زبان متن
      <select value={locale} onChange={e=>{setLocale(e.target.value);setPreview(null);}}>
       {catalog.supported_languages.map(lang=><option key={lang.code} value={lang.code}>{lang.name}</option>)}
      </select>
     </label>
     <label>دسته درخواست اداری
      <select value={intent} onChange={e=>{setIntent(e.target.value as Intent);setPreview(null);}}>
       {catalog.intents.map(key=><option key={key} value={key}>{labels[key]||key}</option>)}
      </select>
     </label>
     <div className="formActions"><button className="button" disabled={busy}>{busy?'در حال دریافت...':'نمایش پاسخ نمونه'}</button></div>
    </form>
    {preview&&<section style={{marginTop:22,padding:18,border:'1px solid #cedae0',borderRadius:12}}>
     <h3>متن ثابتِ پیشنهادی</h3>
     <p dir={direction} lang={preview.language} style={{fontSize:18,lineHeight:2}}>{preview.message}</p>
     <small>ارجاع برای بازبینی انسانی: بله · ارسال خارجی: خیر · تشخیص پزشکی: خیر</small>
    </section>}
   </>}
  </section>
 </Shell>;
}
