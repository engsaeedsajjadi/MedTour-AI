'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Patient={id:string;full_name:string;language:string};
type CaseItem={id:string;patient_id:string;status:string;assigned_operator_id:string|null};
type Staff={id:string;email:string;role:string;active:boolean};
type FollowUp={id:string;case_id:string;patient_id:string;assigned_user_id:string;reason_code:string;due_at:string;status:string};
type Candidate={patient_id:string;basis:string};
const REASONS=['document_reminder','appointment_coordination','travel_coordination','check_in','general_administrative'];
const OUTCOMES=['contact_attempted','human_contact_completed','no_response','no_longer_needed'];

export default function PatientCRM(){
 const [patients,setPatients]=useState<Patient[]>([]);
 const [cases,setCases]=useState<CaseItem[]>([]);
 const [people,setPeople]=useState<Staff[]>([]);
 const [myId,setMyId]=useState('');
 const [role,setRole]=useState('');
 const [patientId,setPatientId]=useState('');
 const [caseId,setCaseId]=useState('');
 const [assignee,setAssignee]=useState('');
 const [dueAt,setDueAt]=useState('');
 const [reason,setReason]=useState(REASONS[0]);
 const [items,setItems]=useState<FollowUp[]>([]);
 const [candidates,setCandidates]=useState<Candidate[]>([]);
 const [choice,setChoice]=useState('');
 const [reviewReference,setReviewReference]=useState('');
 const [followupReference,setFollowupReference]=useState('');
 const [outcome,setOutcome]=useState(OUTCOMES[0]);
 const [working,setWorking]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');

 async function load(){
  const [p,c,me,queue]=await Promise.all([
   request<Patient[]>('/patients?limit=200'),
   request<CaseItem[]>('/cases?limit=200'),
   request<{id:string;role:string}>('/auth/me'),
   request<{items:FollowUp[]}>('/crm/followups?status=open'),
  ]);
  setPatients(p);setCases(c);setMyId(me.id);setRole(me.role);
  setAssignee(old=>old||me.id);
  setPatientId(old=>old||p[0]?.id||'');
  setCaseId(old=>old||c[0]?.id||'');
  setItems(queue.items);
  if(me.role==='admin'){
    const all=await request<Staff[]>('/staff');
    setPeople(all.filter(x=>x.active&&(x.role==='admin'||x.role==='operator')));
  }
 }
 useEffect(()=>{load().catch(e=>setError((e as Error).message))},[]);
 async function run(task:()=>Promise<unknown>,message:string){
  setWorking(true);setError('');setNotice('');
  try{await task();setNotice(message);await load();}
  catch(e){setError((e as Error).message)}finally{setWorking(false)}
 }
 async function schedule(e:React.FormEvent){
  e.preventDefault();
  if(!caseId||!assignee||!dueAt)return;
  await run(()=>request('/crm/followups',{
   method:'POST',
   body:JSON.stringify({case_id:caseId,assigned_user_id:assignee,
    reason_code:reason,due_at:new Date(dueAt).toISOString(),
    idempotency_key:'crm-'+crypto.randomUUID()})
  }),'پیگیری اداری ثبت شد؛ هیچ پیام خودکاری برای بیمار ارسال نشده است.');
 }
 async function resolve(id:string,action:'complete'|'cancel'){
  if(!window.confirm('این اقدام صرفاً ثبت دستی وضعیت پیگیری است. ادامه می‌دهید؟'))return;
  await run(()=>request('/crm/followups/'+encodeURIComponent(id)+'/resolve',{
   method:'POST',body:JSON.stringify(action==='cancel'?{action}:{
    action,outcome_code:outcome,reference:followupReference
   })
  }),'نتیجه پیگیری در CRM و سابقه پرونده ثبت شد.');
  setFollowupReference('');
 }
 async function candidatesFor(){
  if(!patientId)return;
  setError('');setCandidates([]);
  try{
   const r=await request<{candidates:Candidate[]}>('/crm/patients/'+encodeURIComponent(patientId)+'/duplicates');
   setCandidates(r.candidates);
   setChoice(r.candidates[0]?.patient_id||'');
  }catch(e){setError((e as Error).message)}
 }
 async function duplicateDecision(decision:'possible_same'|'distinct'){
  if(!patientId||!choice)return;
  await run(()=>request('/crm/patients/'+encodeURIComponent(patientId)+'/duplicate-review',{
   method:'POST',body:JSON.stringify({candidate_patient_id:choice,decision,reference:reviewReference})
  }),'ارزیابی انسانی ثبت شد. هیچ پرونده، رضایت‌نامه یا هویت پزشکی ادغام نشده است.');
  setReviewReference('');
 }
 const visibleCases=cases.filter(c=>c.patient_id===patientId);
 return <Shell title="Patient CRM — مدیریت ارتباط بیمار">
  <div className="infoBanner">CRM فقط برای هماهنگی اداری و اطلاعات ساختگی است؛ تشخیص هویت، ادغام پرونده، ارسال پیام و تصمیم درمانی خودکار انجام نمی‌شود. تاریخ و ساعت پیگیری با منطقه زمانی دستگاه شما ثبت می‌شود.</div>
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {notice&&<div role="status" className="infoBanner">{notice}</div>}
  <section className="panel" style={{padding:20}}>
   <h2>پرونده‌ها، مسئول هماهنگی و منبع جذب</h2>
   <label>بیمار آزمایشی
    <select value={patientId} onChange={e=>{setPatientId(e.target.value);setCandidates([])}} style={{display:'block',width:'100%',padding:10}}>
     <option value="">انتخاب بیمار</option>
     {patients.map(p=><option key={p.id} value={p.id}>{p.full_name} · {p.language}</option>)}
    </select>
   </label>
   <p>پرونده‌های مرتبط: {visibleCases.length}</p>
   {visibleCases.map(c=><p key={c.id}>پرونده {c.id.slice(0,8)} — {c.status} — مسئول: {c.assigned_operator_id?.slice(0,8)||'تعیین‌نشده'}</p>)}
   {role==='admin'&&patientId&&<div style={{display:'flex',gap:10,flexWrap:'wrap',margin:'10px 0'}}>
    <select value={assignee} onChange={e=>setAssignee(e.target.value)}>
     {people.map(x=><option key={x.id} value={x.id}>{x.email}</option>)}
    </select>
    <button type="button" disabled={working||!assignee} onClick={()=>
     run(()=>request('/crm/patients/'+encodeURIComponent(patientId)+'/assign',{
      method:'POST',body:JSON.stringify({coordinator_user_id:assignee})
     }),'مسئول بیمار ثبت شد.')}>تعیین مسئول بیمار</button>
    {visibleCases.map(c=><button type="button" key={c.id} disabled={working||!assignee} onClick={()=>
     run(()=>request('/crm/cases/'+encodeURIComponent(c.id)+'/assign',{
      method:'POST',body:JSON.stringify({coordinator_user_id:assignee})
     }),'مسئول پرونده ثبت شد.')}>انتساب پرونده {c.id.slice(0,8)}</button>)}
   </div>}
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>برنامه پیگیری انسانی</h2>
   <form onSubmit={schedule} style={{display:'grid',gap:12,maxWidth:680}}>
    <label>پرونده<select required value={caseId} onChange={e=>setCaseId(e.target.value)} style={{display:'block',width:'100%',padding:10}}>
     <option value="">انتخاب پرونده</option>
     {cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.status}</option>)}
    </select></label>
    <label>دلیل اداری<select value={reason} onChange={e=>setReason(e.target.value)} style={{display:'block',width:'100%',padding:10}}>
     {REASONS.map(x=><option key={x} value={x}>{x}</option>)}
    </select></label>
    <label>مسئول پیگیری<select value={assignee} onChange={e=>setAssignee(e.target.value)} style={{display:'block',width:'100%',padding:10}}>
     {(role==='admin'?people:[{id:myId,email:'خودم',role:'operator',active:true}]).map(x=><option key={x.id} value={x.id}>{x.email}</option>)}
    </select></label>
    <label>زمان پیگیری<input type="datetime-local" value={dueAt} onChange={e=>setDueAt(e.target.value)} required style={{display:'block',width:'100%',padding:10}}/></label>
    <button className="button" disabled={working||!dueAt||!caseId}>ثبت پیگیری بدون ارسال پیام</button>
   </form>
   <h3>پیگیری‌های باز (فقط موارد مجاز)</h3>
   <label>کد نتیجه دستی<select value={outcome} onChange={e=>setOutcome(e.target.value)}>
    {OUTCOMES.map(x=><option key={x} value={x}>{x}</option>)}
   </select></label>
   <label>مرجع انجام تماس (بدون نام یا متن پزشکی)
    <input value={followupReference} onChange={e=>setFollowupReference(e.target.value)}
     pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" minLength={6} maxLength={100}/>
   </label>
   {items.length===0?<p>پیگیری بازی در این محدوده وجود ندارد.</p>:items.map(x=><div key={x.id} style={{padding:12,borderBottom:'1px solid #cdd7df'}}>
    <strong>{x.case_id.slice(0,8)}</strong> — {x.reason_code} — {new Date(x.due_at).toLocaleString('fa-IR')}
    <button type="button" disabled={working||!followupReference} style={{margin:6}} onClick={()=>resolve(x.id,'complete')}>ثبت نتیجه</button>
    <button type="button" disabled={working} onClick={()=>resolve(x.id,'cancel')}>لغو</button>
   </div>)}
  </section>
  {role==='admin'&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>بررسی موارد احتمالاً تکراری</h2>
   <p>تطبیق فقط بر پایه شماره تماس یکسان پس از نرمال‌سازی است و اثبات هویت محسوب نمی‌شود.</p>
   <button type="button" disabled={!patientId||working} onClick={candidatesFor}>جستجوی موارد مشابه</button>
   {candidates.length>0&&<div style={{marginTop:12}}>
    <label>نامزد بررسی<select value={choice} onChange={e=>setChoice(e.target.value)}>
     {candidates.map(x=><option key={x.patient_id} value={x.patient_id}>{x.patient_id.slice(0,12)} — تطبیق تماس</option>)}
    </select></label>
    <label>شماره مرجع بررسی انسانی (بدون اطلاعات پزشکی)<input value={reviewReference} onChange={e=>setReviewReference(e.target.value)}
     pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" minLength={6} maxLength={100}/></label>
    <button type="button" disabled={working||reviewReference.length<6} onClick={()=>duplicateDecision('possible_same')}>ثبت احتمال یکسان بودن</button>
    <button type="button" disabled={working||reviewReference.length<6} onClick={()=>duplicateDecision('distinct')}>ثبت متفاوت بودن</button>
   </div>}
  </section>}
 </Shell>;
}
