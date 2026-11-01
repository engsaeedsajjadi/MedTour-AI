'use client';
import {API_BASE} from '@/lib/api';
import {fa,faError,faNetwork} from '@/lib/i18n';
import {useEffect,useState} from 'react';
const description:Record<string,string>={
 intake:'دریافت اطلاعات اولیه درخواست خدمت درمانی، بدون تشخیص پزشکی.',
 medical_documents:'دریافت و نگهداری امن مدارک پزشکی برای بررسی توسط افراد صلاحیت‌دار.',
 communication:'تماس با شما درباره هماهنگی اداری درمان.',
 ai_processing:'استفاده از پردازشگر هوش مصنوعی تأییدشده برای کمک به ترجمه اداری و خلاصه‌سازی مدارک.',
 hospital_coordination:'به اشتراک گذاشتن شناسه اداری پرونده با بیمارستان برای هماهنگی.',
};
type Preview={purpose:string;privacy_notice_url:string|null;privacy_notice_version:string;production_notice_configured:boolean};
async function readJson(r:Response){return r.json().catch(()=>({}));}
export default function Consent(){
 const [token,setToken]=useState(''),[data,setData]=useState<Preview|null>(null),[choice,setChoice]=useState(false),[result,setResult]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  const params=new URLSearchParams(window.location.hash.slice(1));const key=params.get('token')||'';
  window.history.replaceState({},'',window.location.pathname);setToken(key);if(!key)return;
  fetch(`${API_BASE}/api/v1/consent-links/preview?token=${encodeURIComponent(key)}`,{cache:'no-store'})
   .then(async r=>{const v=await readJson(r);if(!r.ok)throw new Error(faError(v.detail,r.status));return v as Preview;})
   .then(setData).catch(e=>setError(faNetwork(e)));
 },[]);
 async function respond(accepted:boolean){
  setError('');setResult('');if(!data)return;setBusy(true);
  try{
   const r=await fetch(`${API_BASE}/api/v1/consent-links/respond`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,notice_version:data.privacy_notice_version,accepted})});
   const v=await readJson(r);if(!r.ok)throw new Error(faError(v.detail,r.status));
   setResult(accepted?'رضایت شما ثبت شد. می‌توانید این صفحه را ببندید.':'انصراف شما ثبت شد. می‌توانید این صفحه را ببندید.');setToken('');setData(null);
  }catch(e){setError(faNetwork(e));}finally{setBusy(false);}
 }
 return <main className="publicCard">
  <div className="publicBrand"><span className="brandMark" aria-hidden="true">✚</span><strong>MedTour AI</strong></div>
  <h1>رضایت‌نامه حریم خصوصی</h1>
  <p className="publicLead">این رضایت برای هماهنگی محرمانه درمان بین‌المللی لازم است. این صفحه تشخیص پزشکی یا خدمات اورژانس ارائه نمی‌دهد.</p>
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {result&&<div role="status" className="successBox">{result}</div>}
  {data&&<>
   <h2>{fa(data.purpose)}</h2>
   <p>{description[data.purpose]||'پردازش داده فقط برای همین هدف مشخص.'}</p>
   <p className="subtle">نسخه اطلاعیه: <span dir="ltr">{data.privacy_notice_version}</span></p>
   {data.privacy_notice_url
    ?<p><a className="textLink" href={data.privacy_notice_url} target="_blank" rel="noopener noreferrer">پیش از تصمیم، اطلاعیه حریم خصوصی را بخوانید</a></p>
    :<div className="infoBanner">نسخه نمایشی: متن نهایی و حقوقی اطلاعیه حریم خصوصی هنوز تنظیم نشده است. با اطلاعات واقعی بیمار استفاده نکنید.</div>}
   <label className="checkRow"><input type="checkbox" checked={choice} onChange={e=>setChoice(e.target.checked)}/> اطلاعیه را خوانده‌ام و با همین هدف مشخص موافقم.</label>
   <div className="buttonRow"><button className="button" disabled={!choice||busy} onClick={()=>respond(true)}>موافقم</button><button className="button secondary" disabled={busy} onClick={()=>respond(false)}>موافق نیستم</button></div>
  </>}
  {!token&&!data&&!result&&!error&&<div className="infoBanner">برای ثبت رضایت به لینک دعوت اختصاصی نیاز است.</div>}
 </main>;
}
