'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type User={id:string;email:string;role:string;active:boolean};
type Assigned={session_id:string;case_id:string;language:string;status:string};
type Queue={items:Array<{id:string;case_id:string;status:string;language:string}>};
type AssignedResult={items:Assigned[];raw_medical_answers_included:boolean};
const choices=[
 ['additional_information_requested','درخواست اطلاعات تکمیلی'],
 ['external_clinical_assessment_required','نیازمند ارزیابی پزشکی مستقل'],
 ['nonclinical_handoff_acknowledged','تأیید دریافت اداری ارجاع']
] as const;

export default function ReviewerWorkspace(){
 const [role,setRole]=useState('');
 const [staff,setStaff]=useState<User[]>([]);
 const [sessions,setSessions]=useState<Queue['items']>([]);
 const [mine,setMine]=useState<Assigned[]>([]);
 const [reviewer,setReviewer]=useState('');
 const [session,setSession]=useState('');
 const [country,setCountry]=useState('IR');
 const [authority,setAuthority]=useState('');
 const [verification,setVerification]=useState('');
 const [expiry,setExpiry]=useState('');
 const [action,setAction]=useState<string>(choices[0][0]);
 const [reference,setReference]=useState('');
 const [busy,setBusy]=useState(false);
 const [message,setMessage]=useState('');
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 useEffect(()=>{
  (async()=>{
   const me=await request<{role:string}>('/auth/me');setRole(me.role);
   if(me.role==='admin'){
    const [u,q]=await Promise.all([request<User[]>('/staff'),request<Queue>('/intake-coordination/queue')]);
    const physicians=u.filter(p=>p.role==='physician'&&p.active);
    const eligible=q.items.filter(x=>x.status==='awaiting_clinician_review');
    setStaff(physicians);setReviewer(physicians[0]?.id||'');setSessions(eligible);setSession(eligible[0]?.id||'');
   }
   if(me.role==='physician'){
    const mine=await request<AssignedResult>('/intake-review/my-assignments');
    setMine(mine.items);setSession(mine.items[0]?.session_id||'');
   }
  })().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 async function run(fn:()=>Promise<unknown>,success:string){
  setBusy(true);setError('');setMessage('');
  try{await fn();setMessage(success);}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function credential(e:React.FormEvent){
  e.preventDefault();if(!reviewer||!expiry)return;
  await run(()=>request('/intake-review/reviewers/'+encodeURIComponent(reviewer)+'/credential',{
   method:'PUT',body:JSON.stringify({
    issuing_country:country.toUpperCase(),issuing_authority:authority.trim(),
    verification_reference:verification.trim(),expires_at:new Date(expiry).toISOString()
   })
  }),'شواهد بررسی محلی صلاحیت ثبت شد. این اقدام، تأیید مستقل صلاحیت پزشکی نیست.');
 }
 async function assign(e:React.FormEvent){
  e.preventDefault();if(!reviewer||!session)return;
  await run(()=>request('/intake-review/sessions/'+encodeURIComponent(session)+'/assignment',{
   method:'POST',body:JSON.stringify({reviewer_user_id:reviewer})
  }),'بازبین تنها به این پذیرش آزمایشی منتسب شد؛ تصمیم پزشکی صادر نشد.');
 }
 async function recommend(e:React.FormEvent){
  e.preventDefault();if(!session)return;
  await run(async()=>{
   await request('/intake-review/sessions/'+encodeURIComponent(session)+'/recommendation',{
    method:'POST',body:JSON.stringify({action,reference:reference.trim()})
   });
   const refreshed=await request<AssignedResult>('/intake-review/my-assignments');setMine(refreshed.items);
   setReference('');
  },'پیشنهاد هماهنگی ثبت شد؛ این اقدام تشخیص، تأیید درمان یا رفع هشدار نیست.');
 }
 return <Shell title="بازبینی پذیرش و ارجاع تخصصی">
  <div className="infoBanner">
   فقط محیط توسعه با داده ساختگی. نقش پزشک یا بررسی محلی مدرک به‌تنهایی اعتبار حرفه‌ای مستقل را تأیید نمی‌کند. این پنل به اطلاعات پزشکی خام دسترسی نمی‌دهد؛ تصمیم‌ها باید در فرایند بالینی معتبر و خارج از این نسخه تأیید شوند.
  </div>
  {loading&&<p>در حال بررسی نقش و مجوز...</p>}
  {error&&<p role="alert" className="errorBox">{error}</p>}
  {message&&<p role="status" className="infoBanner">{message}</p>}
  {role==='admin'&&<div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(300px,1fr))',gap:18}}>
   <section className="panel" style={{padding:20}}>
    <h2>ثبت شواهد اعتبارسنجی محلی پزشک</h2>
    <form onSubmit={credential} style={{display:'grid',gap:12}}>
     <label>حساب پزشک<select required value={reviewer} onChange={e=>setReviewer(e.target.value)} style={{display:'block',width:'100%',padding:10}}>
      {staff.map(u=><option key={u.id} value={u.id}>{u.email}</option>)}</select></label>
     <label>کشور مرجع (دو حرف لاتین)<input required pattern="[A-Z]{2}" maxLength={2} value={country} onChange={e=>setCountry(e.target.value.toUpperCase())} style={{display:'block',width:'100%',padding:10}}/></label>
     <label>مرجع صادرکننده<input required minLength={3} maxLength={120} value={authority} onChange={e=>setAuthority(e.target.value)} style={{display:'block',width:'100%',padding:10}}/></label>
     <label>شناسه مدرک بررسی‌شده (بدون اطلاعات پزشکی)<input required minLength={6} maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" value={verification} onChange={e=>setVerification(e.target.value)} style={{display:'block',width:'100%',padding:10}}/></label>
     <label>انقضا<input required type="datetime-local" value={expiry} onChange={e=>setExpiry(e.target.value)} style={{display:'block',width:'100%',padding:10}}/></label>
     <button className="button" disabled={busy||!reviewer}>ثبت شواهد محلی</button>
    </form>
   </section>
   <section className="panel" style={{padding:20}}>
    <h2>انتساب بازبین به فرم مشخص</h2>
    <form onSubmit={assign} style={{display:'grid',gap:12}}>
     <label>پرونده پذیرش<select required value={session} onChange={e=>setSession(e.target.value)} style={{display:'block',width:'100%',padding:10}}>
      {sessions.map(x=><option key={x.id} value={x.id}>{x.case_id.slice(0,8)} — {x.language}</option>)}</select></label>
     <p>شناسه حساب انتخاب‌شده: <code>{reviewer.slice(0,12)}</code></p>
     <button className="button" disabled={busy||!reviewer||!session}>ثبت انتساب محدود</button>
    </form>
    <div style={{display:'flex',flexWrap:'wrap',gap:8,marginTop:14}}>
     <button type="button" disabled={busy||!reviewer} onClick={()=>{
      if(!window.confirm('آیا بررسی محلی مدرک این پزشک لغو شود؟'))return;
      void run(()=>request('/intake-review/reviewers/'+encodeURIComponent(reviewer)+'/revoke',{method:'POST'}),'اعتبارسنجی محلی غیرفعال شد.');
     }}>لغو صلاحیت محلی ثبت‌شده</button>
     <button type="button" disabled={busy||!reviewer||!session} onClick={()=>{
      if(!window.confirm('آیا دسترسی پزشک به این پذیرش لغو شود؟'))return;
      void run(()=>request('/intake-review/sessions/'+encodeURIComponent(session)+'/assignment/'+encodeURIComponent(reviewer)+'/revoke',{method:'POST'}),'انتساب پزشک به پذیرش لغو شد.');
     }}>لغو انتساب بازبین</button>
    </div>
    <p>تنها پس از ثبت شواهد معتبر محلی، امکان انتساب بازبین وجود دارد. انتساب به معنی مجوز تأیید درمان نیست.</p>
   </section>
  </div>}
  {role==='physician'&&<section className="panel" style={{padding:20}}>
   <h2>فرم‌های منتسب‌شده به شما</h2>
   {mine.length===0?<p>پذیرش دارای مجوز و انتساب فعال یافت نشد.</p>:<form onSubmit={recommend} style={{display:'grid',gap:12,maxWidth:650}}>
    <label>شناسه فرم<select value={session} onChange={e=>setSession(e.target.value)} required style={{display:'block',width:'100%',padding:10}}>
     {mine.map(x=><option key={x.session_id} value={x.session_id}>{x.case_id.slice(0,8)} — {x.language} — {x.status}</option>)}
    </select></label>
    <label>نوع توصیه اداری<select value={action} onChange={e=>setAction(e.target.value)} required style={{display:'block',width:'100%',padding:10}}>
     {choices.map(([key,title])=><option value={key} key={key}>{title}</option>)}</select></label>
    <label>مرجع پیگیری (بدون اطلاعات پزشکی)<input required pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" minLength={6} maxLength={100}
     value={reference} onChange={e=>setReference(e.target.value)} style={{display:'block',width:'100%',padding:10}}/></label>
    <button className="button" disabled={busy||!session}>ثبت توصیه غیرتشخیصی</button>
   </form>}
  </section>}
  {!loading&&role!=='admin'&&role!=='physician'&&<p>دسترسی این صفحه فقط برای مدیر و پزشک منتسب به پذیرش تعریف شده است.</p>}
 </Shell>;
}
