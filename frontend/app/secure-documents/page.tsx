'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {API_BASE,getSession,request} from '@/lib/api';
type CaseRow={id:string;status:string;specialty:string};
type MedicalDoc={id:string;filename:string;status:string;category:string;created_at:string};
type Readiness={storage_mode:string;configured:boolean;actual_s3_kms_scanner_verified:boolean;production_ready:boolean};
export default function Documents(){
 const [cases,setCases]=useState<CaseRow[]>([]);
 const [caseId,setCaseId]=useState('');
 const [file,setFile]=useState<File|null>(null);
 const [documents,setDocuments]=useState<MedicalDoc[]>([]);
 const [readiness,setReadiness]=useState<Readiness|null>(null);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [error,setError]=useState(''),[message,setMessage]=useState('');
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
   const data=await r.json();
   if(!r.ok)throw new Error(String(data.detail||r.status));
   setMessage('فایل ساختگی با وضعیت '+data.status+' ذخیره شد. این محیط برای اطلاعات واقعی بیماران نیست.');
   setFile(null);await refresh();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function download(d:MedicalDoc){
  setBusy(true);setError('');
  try{
   const r=await fetch(API_BASE+'/api/v1/secure-documents/'+encodeURIComponent(d.id),{
    headers:{Authorization:'Bearer '+getSession()},cache:'no-store'
   });
   if(!r.ok)throw new Error('دسترسی به فایل مجاز نیست ('+r.status+').');
   const blob=await r.blob(),url=URL.createObjectURL(blob);
   const link=document.createElement('a');link.href=url;link.download='synthetic-document';
   document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="مدیریت امن مدارک">
  <div className="infoBanner">نسخه Alpha برای اطلاعات پزشکی واقعی مجاز نیست. فایل محلی AES-GCM رمزنگاری می‌شود ولی اسکن نمی‌شود؛ S3/KMS/ClamAV و سیاست نگهداری نیازمند تأیید مستقل‌اند.</div>
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {message&&<p className="infoBanner" role="status">{message}</p>}
  <section className="panel" style={{padding:20}}>
   <h2>وضعیت مخزن امن</h2>
   <p>حالت: <strong>{readiness?.storage_mode||'در حال بررسی...'}</strong></p>
   <p>اتصال واقعی S3/KMS/اسکنر: {readiness?.actual_s3_kms_scanner_verified?'تأییدشده':'تأییدنشده'}</p>
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
    <button className="button" disabled={busy||!file||!caseId||!readiness?.configured}>بارگذاری آزمایشی</button>
   </form>
   <p>فایل‌های قبلی پس از لغو رضایت مسدود می‌شوند و با رضایت جدید خودکار باز نمی‌گردند.</p>
   <div className="tableScroll"><table><thead><tr><th>نام فایل</th><th>وضعیت</th><th>تاریخ</th><th>دسترسی</th></tr></thead>
    <tbody>{documents.length===0?<tr><td colSpan={4}>فایل دارای دسترسی موجود نیست.</td></tr>:documents.map(d=><tr key={d.id}>
     <td>{d.filename}</td><td>{d.status}</td><td>{new Date(d.created_at).toLocaleString('fa-IR')}</td>
     <td><button type="button" disabled={busy} onClick={()=>download(d)}>دریافت امن</button></td>
    </tr>)}</tbody></table></div>
  </section>
 </Shell>;
}
