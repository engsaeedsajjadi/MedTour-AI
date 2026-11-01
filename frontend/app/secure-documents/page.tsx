'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {API_BASE,getSession,request} from '@/lib/api';
import {fa,faError} from '@/lib/i18n';
type CaseRow={id:string;status:string;specialty:string};
type MedicalDoc={id:string;filename:string;status:string;category:string;created_at:string};
type RetentionDoc={id:string;filename:string;status:string;created_at:string;legal_hold:boolean;erased_at:string|null;erasure_due:boolean};
type Retention={documents:RetentionDoc[];retention_days:number|null};
type Readiness={storage_mode:string;configured:boolean;actual_s3_kms_scanner_verified:boolean;production_ready:boolean};
export default function Documents(){
 const [cases,setCases]=useState<CaseRow[]>([]);
 const [caseId,setCaseId]=useState('');
 const [file,setFile]=useState<File|null>(null);
 const [documents,setDocuments]=useState<MedicalDoc[]>([]);
 const [readiness,setReadiness]=useState<Readiness|null>(null);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [error,setError]=useState(''),[message,setMessage]=useState('');
 const [role,setRole]=useState(''),[retention,setRetention]=useState<Retention|null>(null),[reference,setReference]=useState('');
 useEffect(()=>{request<{role:string}>('/auth/me').then(x=>setRole(x.role)).catch(()=>{});},[]);
 useEffect(()=>{setRetention(null);if(!caseId||role!=='admin')return;
  request<Retention>('/secure-documents/cases/'+encodeURIComponent(caseId)+'/retention-review').then(setRetention).catch(e=>setError((e as Error).message));
 },[caseId,role]);
 async function governance(path:string,body:object,confirmText:string){
  if(!window.confirm(confirmText))return;
  setBusy(true);setError('');setMessage('');
  try{await request(path,{method:'POST',body:JSON.stringify(body)});
   setMessage('عملیات ثبت شد و در گزارش ممیزی ذخیره شد.');
   setRetention(await request<Retention>('/secure-documents/cases/'+encodeURIComponent(caseId)+'/retention-review'));await refresh();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 useEffect(()=>{
  Promise.all([request<CaseRow[]>('/cases'),request<Readiness>('/secure-documents/readiness')])
   .then(([cs,r])=>{setCases(cs);setCaseId(cs[0]?.id||'');setReadiness(r);})
   .catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 useEffect(()=>{
  setDocuments([]);if(!caseId)return;
  request<MedicalDoc[]>('/secure-documents/cases/'+encodeURIComponent(caseId)+'/list')
   .then(setDocuments).catch(e=>setError((e as Error).message));
 },[caseId]);
 async function refresh(){
  if(caseId)setDocuments(await request<MedicalDoc[]>('/secure-documents/cases/'+encodeURIComponent(caseId)+'/list'));
 }
 async function upload(e:React.FormEvent){
  e.preventDefault();if(!file||!caseId)return;
  if(file.size>8*1024*1024){setError('فایل بزرگ‌تر از ۸ مگابایت است.');return;}
  setBusy(true);setError('');setMessage('');
  try{
   const fd=new FormData();fd.append('file',file);
   const r=await fetch(API_BASE+'/api/v1/secure-documents/cases/'+encodeURIComponent(caseId),{
    method:'POST',headers:{Authorization:'Bearer '+getSession()},body:fd,cache:'no-store'
   });
   const data=await r.json().catch(()=>({}));
   if(!r.ok)throw new Error(faError(data.detail,r.status));
   setMessage('فایل با وضعیت «'+fa(data.status)+'» ذخیره شد. این نسخه برای اطلاعات واقعی بیماران نیست.');
   setFile(null);await refresh();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function download(d:MedicalDoc){
  setBusy(true);setError('');
  try{
   const r=await fetch(API_BASE+'/api/v1/secure-documents/'+encodeURIComponent(d.id),{
    headers:{Authorization:'Bearer '+getSession()},cache:'no-store'
   });
   if(!r.ok){const body=await r.json().catch(()=>({}));throw new Error(faError(body.detail,r.status));}
   const blob=await r.blob(),url=URL.createObjectURL(blob);
   const link=document.createElement('a');link.href=url;link.download=d.filename||'medical-document';
   document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="مدیریت امن مدارک">
  <div className="infoBanner">نسخه نمایشی برای اطلاعات پزشکی واقعی مجاز نیست. فایل‌ها رمزنگاری می‌شوند ولی اسکن بدافزار نمی‌شوند؛ مخزن ابری امن، اسکن فایل و سیاست نگهداری پیش از استفاده واقعی باید تأیید شوند.</div>
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {message&&<p className="infoBanner" role="status">{message}</p>}
  <section className="panel" style={{padding:20}}>
   <h2>وضعیت مخزن امن</h2>
   <p>حالت: <strong>{readiness?fa(readiness.storage_mode):'در حال بررسی...'}</strong></p>
   <p>مخزن ابری امن و اسکن بدافزار: {readiness?.storage_mode==='s3_kms_configured_unverified'?'پیکربندی‌شده':'پیکربندی نشده'}</p>
   <p>مجاز برای اطلاعات بیمار واقعی: <strong>خیر</strong></p>
  </section>
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>پرونده آزمایشی و فایل‌های مجاز</h2>
   {loading?<p>در حال دریافت...</p>:<label>پرونده
    <select aria-label="انتخاب پرونده" value={caseId} onChange={e=>{setError('');setCaseId(e.target.value)}} style={{display:'block',width:'100%',padding:10}}>
     {cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.specialty||c.status}</option>)}
    </select>
   </label>}
   <form onSubmit={upload} style={{display:'flex',flexWrap:'wrap',gap:10,margin:'16px 0'}}>
    <input aria-label="فایل آزمایشی" type="file" accept=".pdf,.jpg,.jpeg,.png" required onChange={e=>setFile(e.target.files?.[0]||null)}/>
    <button className="button" disabled={busy||!file||!caseId||!readiness?.configured}>بارگذاری امن</button>
   </form>
   <p>فایل‌های قبلی پس از لغو رضایت مسدود می‌شوند و با رضایت جدید خودکار باز نمی‌گردند.</p>
   <div className="tableScroll"><table><thead><tr><th>نام فایل</th><th>وضعیت</th><th>تاریخ</th><th>دسترسی</th></tr></thead>
    <tbody>{documents.length===0?<tr><td colSpan={4}>فایل دارای دسترسی موجود نیست.</td></tr>:documents.map(d=><tr key={d.id}>
     <td>{d.filename}</td><td>{fa(d.status)}</td><td>{new Date(d.created_at).toLocaleString('fa-IR')}</td>
     <td><button type="button" disabled={busy} onClick={()=>download(d)}>دریافت امن</button></td>
    </tr>)}</tbody></table></div>
  </section>
  {role==='admin'&&<section className="panel" style={{padding:20,marginTop:18}}>
   <h2>بازبینی نگهداری و حذف مدارک</h2>
   <p>لغو رضایت فقط دسترسی را می‌بندد. «حذف رمزنگاری‌شده» کلید رمزگشایی و فایل ذخیره‌شده را برای همیشه از بین می‌برد و فقط سابقه ممیزی باقی می‌ماند. سند در توقیف قانونی حذف نمی‌شود.</p>
   <p>دوره نگهداری سازمان: <strong>{retention?.retention_days?retention.retention_days.toLocaleString('fa-IR')+' روز':'تعریف نشده (فقط اسناد لغوشده قابل حذف‌اند)'}</strong></p>
   <label>شماره مرجع تصمیم (درخواست بیمار یا مصوبه حقوقی)<input dir="ltr" minLength={6} maxLength={100} value={reference} onChange={e=>setReference(e.target.value)} placeholder="ERASE-2026-0001"/></label>
   <div className="tableScroll"><table><thead><tr><th>نام فایل</th><th>وضعیت</th><th>توقیف قانونی</th><th>اقدام</th></tr></thead>
    <tbody>{!retention||retention.documents.length===0?<tr><td colSpan={4} className="empty">سندی در انتظار تصمیم نگهداری نیست.</td></tr>:retention.documents.map(d=><tr key={d.id}>
     <td dir="auto">{d.filename}</td><td>{fa(d.status)}</td><td>{d.legal_hold?'بله':'خیر'}</td>
     <td style={{display:'flex',gap:8,flexWrap:'wrap'}}>{d.erased_at?'حذف شده در '+new Date(d.erased_at).toLocaleString('fa-IR'):<>
      <button type="button" disabled={busy||reference.length<6} onClick={()=>void governance('/secure-documents/'+d.id+'/legal-hold',{reference,legal_hold:!d.legal_hold},d.legal_hold?'توقیف قانونی این سند برداشته شود؟':'این سند در توقیف قانونی قرار گیرد؟')}>{d.legal_hold?'رفع توقیف':'توقیف قانونی'}</button>
      {d.erasure_due&&<button type="button" className="button" disabled={busy||reference.length<6} onClick={()=>void governance('/secure-documents/'+d.id+'/erase',{reference},'این سند برای همیشه و بدون امکان بازگشت حذف می‌شود. ادامه می‌دهید؟')}>حذف رمزنگاری‌شده</button>}
     </>}</td>
    </tr>)}</tbody></table></div>
  </section>}
 </Shell>;
}
