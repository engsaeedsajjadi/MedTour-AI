'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
type Case={id:string;status:string;specialty:string};
type Option={physician_id:string;name:string;specialty:string;city:string;reason:string};
type Proposal={id:string;physician_id:string;hospital_id:string|null;status:string;review_reference:string|null;clinical_suitability_determined:boolean};
type Hospital={id:string;name:string};
export default function ProviderMatching(){
 const [cases,setCases]=useState<Case[]>([]);
 const [hospitals,setHospitals]=useState<Hospital[]>([]);
 const [caseId,setCaseId]=useState('');
 const [doctor,setDoctor]=useState('');
 const [hospital,setHospital]=useState('');
 const [options,setOptions]=useState<Option[]>([]);
 const [proposals,setProposals]=useState<Proposal[]>([]);
 const [role,setRole]=useState('');
 const [reference,setReference]=useState('');
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const ROOT='/provider-matching';
 async function reload(id=caseId){
  if(!id)return;
  const [a,b]=await Promise.all([
   request<{items:Option[]}>(ROOT+'/cases/'+encodeURIComponent(id)+'/options'),
   request<{items:Proposal[]}>(ROOT+'/cases/'+encodeURIComponent(id)+'/proposals')
  ]);
  setOptions(a.items);setProposals(b.items);
  setDoctor(old=>a.items.some(x=>x.physician_id===old)?old:(a.items[0]?.physician_id||''));
 }
 useEffect(()=>{(async()=>{
  const [me,cs,hs]=await Promise.all([
   request<{role:string}>('/auth/me'),
   request<Case[]>('/cases?limit=200'),
   request<Hospital[]>('/hospitals'),
  ]);
  setRole(me.role);setCases(cs);setHospitals(hs);
  setCaseId(cs[0]?.id||'');
  if(cs[0])await reload(cs[0].id);
 })().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 async function action(path:string,body:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method:'POST',body:JSON.stringify(body)});
   setNotice('تصمیم اداری ثبت شد؛ تأیید درمان، مجوز پزشکی یا رزرو انجام نشده است.');
   await reload();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="تطبیق اداری بیمار با ارائه‌دهندگان خدمات">
  <div className="infoBanner">این ابزار صرفاً گزینه‌های اداری را بر اساس متن تخصص و شواهد محلی بررسی‌نشده توسط مرجع مستقل معرفی می‌کند. تطبیق پزشکی، تشخیص، رتبه‌بندی بالینی، معرفی قطعی پزشک و رزرو خودکار انجام نمی‌شود. فقط داده ساختگی.</div>
  {loading&&<p>در حال بارگذاری...</p>}
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {notice&&<div role="status" className="infoBanner">{notice}</div>}
  {!loading&&<>
   <section className="panel" style={{padding:20}}>
    <h2>پرونده و گزینه‌های اولیه</h2>
    <label>پرونده
     <select value={caseId} onChange={e=>{const v=e.target.value;setCaseId(v);setError('');void reload(v).catch(err=>setError((err as Error).message))}} style={{display:'block',width:'100%',padding:10}}>
      {cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.specialty} — {c.status}</option>)}
     </select>
    </label>
    <p>گزینه‌های مطابق متن تخصص: {options.length}. این فهرست تضمین‌کننده پوشش جامع یا کیفیت پزشکی نیست.</p>
    {options.map(o=><p key={o.physician_id}><strong>{o.name}</strong> — {o.specialty} — {o.city}<small> | شواهد محلی منقضی‌نشده؛ استعلام مستقل انجام نشده</small></p>)}
    <div style={{display:'grid',gap:10,maxWidth:640}}>
     <label>پزشک پیشنهادی<select value={doctor} onChange={e=>setDoctor(e.target.value)}>
      {options.map(o=><option key={o.physician_id} value={o.physician_id}>{o.name}</option>)}
     </select></label>
     <label>مرکز درمانی اختیاری (تنها در صورت وجود ارتباط و خدمت ثبت‌شده)
      <select value={hospital} onChange={e=>setHospital(e.target.value)}>
       <option value="">بدون بیمارستان</option>
       {hospitals.map(h=><option key={h.id} value={h.id}>{h.name}</option>)}
      </select>
     </label>
     <button disabled={busy||!caseId||!doctor} onClick={()=>void action(ROOT+'/cases/'+encodeURIComponent(caseId)+'/proposals',{physician_id:doctor,hospital_id:hospital||null})}>ثبت گزینه برای بازبینی انسانی</button>
    </div>
   </section>
   <section className="panel" style={{padding:20,marginTop:16}}>
    <h2>بررسی پیشنهادهای ثبت‌شده</h2>
    <label>مرجع بازبینی اداری (بدون اطلاعات پزشکی)
     <input value={reference} minLength={6} maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" onChange={e=>setReference(e.target.value)}/>
    </label>
    {proposals.length===0?<p>پیشنهادی ثبت نشده است.</p>:proposals.map(p=><div key={p.id} style={{padding:12,borderBottom:'1px solid #dde2e8'}}>
     <p>پزشک {p.physician_id.slice(0,10)} · {p.status} · بیمارستان {p.hospital_id?.slice(0,10)||'ندارد'}</p>
     {role==='admin'&&p.status==='pending_human_review'&&<div style={{display:'flex',gap:9}}>
      <button disabled={busy||reference.length<6} onClick={()=>void action(ROOT+'/proposals/'+encodeURIComponent(p.id)+'/review',{decision:'administratively_shortlisted',reference})}>تأیید فقط برای فهرست اداری</button>
      <button disabled={busy||reference.length<6} onClick={()=>void action(ROOT+'/proposals/'+encodeURIComponent(p.id)+'/review',{decision:'rejected',reference})}>رد پیشنهاد</button>
     </div>}
    </div>)}
    <p>«فهرست اداری» هیچ مجوزی برای ارجاع بالینی، شروع درمان یا نوبت‌دهی صادر نمی‌کند.</p>
   </section>
  </>}
 </Shell>;
}
