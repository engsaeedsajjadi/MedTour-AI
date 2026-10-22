'use client';
import {useCallback,useEffect,useState} from 'react';
import Link from 'next/link';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Module = {key:string;label:string;route:string;status:string;master_section:number};
type CaseRow = {id:string;specialty:string;status:string};
type TaskRow = {id:string;status:string;created_at:string};
type Workspace = {
 case_id:string;status:string;specialty:string;
 counts:Record<string,number>;tasks:TaskRow[];tasks_truncated:boolean;
 readiness:Record<string,boolean>;urgent_intake_detected:boolean;
 note:string;production_ready:boolean;
};
const routes:Record<string,string>={
 intake:'/journey',documents:'/secure-documents',physicians:'/providers',
 appointments:'/appointments',quotes:'/quotations',travel:'/travel',
 services:'/operations',conversations:'/conversations',tasks:'/cases'
};
const labels:Record<string,string>={
 intake:'پذیرش',documents:'مدارک',physicians:'ارجاع پزشک',
 appointments:'نوبت‌ها',quotes:'پیش‌فاکتورها',travel:'سفر و ویزا',
 services:'خدمات',conversations:'مکالمات',tasks:'وظایف',tasks_open:'وظایف باز'
};
const stateLabel:Record<string,string>={
 local_workflow:'گردش‌کار داخلی موجود',partial:'نیازمند تکمیل تخصصی',
 external_gate:'نیازمند تأیید خارجی',not_delivered:'تحویل‌نشده'
};
export default function EnterpriseModules() {
 const [modules,setModules]=useState<Module[]>([]);
 const [cases,setCases]=useState<CaseRow[]>([]);
 const [caseId,setCaseId]=useState('');
 const [workspace,setWorkspace]=useState<Workspace|null>(null);
 const [title,setTitle]=useState('');
 const [updating,setUpdating]=useState(false);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [message,setMessage]=useState('');

 const loadWorkspace=useCallback(async (id:string)=>{
   const data=await request<Workspace>('/modules/cases/'+encodeURIComponent(id));
   setWorkspace(data);
 },[]);
 useEffect(()=>{
  Promise.all([request<{modules:Module[]}>('/modules'),request<CaseRow[]>('/cases')])
   .then(([catalog,rows])=>{setModules(catalog.modules);setCases(rows);setCaseId(rows[0]?.id||'');})
   .catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 useEffect(()=>{
  if(!caseId){setWorkspace(null);return;}
  setWorkspace(null);setError('');
  loadWorkspace(caseId).catch(e=>setError((e as Error).message));
 },[caseId,loadWorkspace]);

 async function addTask(e:React.FormEvent){
  e.preventDefault();if(!caseId)return;
  setError('');setMessage('');setUpdating(true);
  try{
   await request('/tasks',{method:'POST',body:JSON.stringify({case_id:caseId,title:title.trim()})});
   setTitle('');await loadWorkspace(caseId);setMessage('وظیفه اداری ثبت شد.');
  }catch(e){setError((e as Error).message)}
  finally{setUpdating(false)}
 }
 async function changeTask(id:string,current:string){
  if(!caseId)return;
  const next=current==='open'?'done':'open';
  const ref=window.prompt('مرجع اداری (حداقل ۶ کاراکتر، بدون اطلاعات شخصی بیمار):');
  if(!ref)return;
  setError('');setMessage('');setUpdating(true);
  try{
   await request('/modules/cases/'+encodeURIComponent(caseId)+'/tasks/'+encodeURIComponent(id)+'/status',{
    method:'PATCH',body:JSON.stringify({status:next,reference:ref.trim()})
   });
   await loadWorkspace(caseId);
   setMessage('وضعیت وظیفه همراه با سوابق Audit ثبت شد.');
  }catch(e){setError((e as Error).message)}
  finally{setUpdating(false)}
 }
 return <Shell title="مرکز یکپارچه ماژول‌ها">
  <div className="infoBanner">این پنل نمای اداری داده‌های موجود است؛ امکانات تخصصی و اتصال واقعی بیمارستان، ویزا، پرداخت و خدمات درمانی را تأیید نمی‌کند. استفاده از اطلاعات پزشکی واقعی مجاز نیست.</div>
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {message&&<div role="status" className="infoBanner">{message}</div>}
  <section className="panel" style={{padding:20,marginBottom:20}}>
   <h2>ماژول‌های سامانه</h2>
   <p>فهرست واقعی امکانات موجود و وضعیت تکمیل هر ماژول در پرامپت Enterprise</p>
   {loading?<p>در حال دریافت...</p>:<div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(210px,1fr))',gap:12}}>
    {modules.map(m=><Link key={m.key} href={m.route} style={{border:'1px solid #d3dce3',padding:14,borderRadius:10,textDecoration:'none',color:'inherit'}}>
     <strong>{m.label}</strong><p style={{margin:'6px 0'}}><small>{stateLabel[m.status]||m.status}</small></p><small>بخش {m.master_section} پرامپت</small>
    </Link>)}
   </div>}
  </section>
  <section className="panel" style={{padding:20}}>
   <h2>پرونده و ارتباط ماژول‌ها</h2>
   {cases.length===0?<p>برای نمایش مرکز یکپارچه ابتدا پرونده آزمایشی ایجاد کنید.</p>:<>
    <label>انتخاب پرونده
     <select aria-label="پرونده" value={caseId} onChange={e=>setCaseId(e.target.value)} style={{display:'block',padding:10,width:'100%'}}>
      {cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.specialty||'بدون تخصص'} — {c.status}</option>)}
     </select>
    </label>
    {!workspace?<p>در حال دریافت نمای یکپارچه پرونده...</p>:<>
     <p><strong>مرحله پرونده:</strong> {workspace.status}</p>
     {workspace.urgent_intake_detected&&<div role="alert" className="errorBox">هشدار اورژانسی ثبت شده است. ارجاع فوری انسانی لازم است؛ این سیستم ابزار تشخیص یا تریاژ نیست.</div>}
     <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(170px,1fr))',gap:10,margin:'14px 0'}}>
      {Object.entries(workspace.counts).map(([key,count])=><Link href={routes[key]||'/journey'} key={key} style={{border:'1px solid #d3dce3',borderRadius:8,padding:12,color:'inherit',textDecoration:'none'}}>
       <small>{labels[key]||key}</small><div style={{fontSize:24,fontWeight:700}}>{count}</div>
      </Link>)}
     </div>
     <h3>شواهد ثبت‌شده برای پیگیری پرونده</h3>
     <div style={{display:'flex',flexWrap:'wrap',gap:10,marginBottom:18}}>
      {Object.entries(workspace.readiness).map(([key,ok])=><span key={key} className="badge" style={{padding:8}}>{ok?'✓':'–'} {key.replaceAll('_',' ')}</span>)}
     </div>
     <h3>وظایف هماهنگی</h3>
     <p>عنوان وظایف را فقط برای کارهای اداری و بدون اطلاعات پزشکی بنویسید.</p>
     <form onSubmit={addTask} style={{display:'flex',flexWrap:'wrap',gap:10,marginBottom:16}}>
      <input aria-label="عنوان وظیفه" minLength={3} maxLength={200} required value={title}
       onChange={e=>setTitle(e.target.value)} placeholder="مثلاً پیگیری تأیید وقت آزمایشی" style={{flex:'1 1 260px',padding:10}}/>
      <button className="button" disabled={updating||!title.trim()}>ثبت وظیفه</button>
     </form>
     <div className="tableScroll"><table><thead><tr><th>شناسه وظیفه</th><th>وضعیت</th><th>تاریخ ثبت</th><th>عملیات</th></tr></thead>
      <tbody>{workspace.tasks.length===0?<tr><td colSpan={4}>وظیفه‌ای ثبت نشده است.</td></tr>:workspace.tasks.map(t=><tr key={t.id}>
       <td><code>{t.id.slice(0,8)}…</code></td><td>{t.status}</td>
       <td>{new Date(t.created_at).toLocaleString('fa-IR')}</td>
       <td><button type="button" className="button secondary" disabled={updating} onClick={()=>changeTask(t.id,t.status)}>{t.status==='open'?'تکمیل':'بازگشایی'}</button></td>
      </tr>)}</tbody></table></div>
     {workspace.tasks_truncated&&<p>فقط ۱۰۰ وظیفه آخر نمایش داده می‌شود.</p>}
    </>}
   </>}
  </section>
 </Shell>;
}
