'use client';

import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type CaseRow={id:string;patient_id:string;status:string};
type CheckRow={item_key:string;status:string;review_reference:string|null};
type Visa={id:string;case_id:string;origin_country:string;destination_country:string;
 status:string;decision_reported:string|null;authority_name:string|null;
 external_reference:string|null;next_action_due_at:string|null;checklist:CheckRow[];
 official_visa_issued_verified:boolean;external_submission_verified:boolean};
type Event={id:string;action:string;previous:string;current:string;reference:string;at:string};
const ROOT='/visa-coordination';
const LABELS:Record<string,string>={
 requested:'درخواست داخلی',in_review:'در حال بررسی',
 ready_for_manual_submission:'آماده ارسال دستی',submission_reported:'ارسال گزارش‌شده',
 outcome_reported:'نتیجه گزارش‌شده',cancelled:'لغوشده',blocked:'مسدود به‌دلیل لغو رضایت',
 identity_document:'مدرک هویتی (صرفاً وضعیت)',provider_invitation:'دعوت‌نامه مرکز درمانی',
 travel_plan:'برنامه سفر',application_forms:'فرم‌های درخواست',
 pending:'بررسی نشده',received:'دریافت‌شده',needs_update:'نیازمند اصلاح',
 locally_reviewed:'بازبینی اداری داخلی',issued_reported:'صدور گزارش‌شده (تأیید نشده)',
 refused_reported:'رد گزارش‌شده',additional_information_reported:'درخواست اطلاعات تکمیلی'
};
const title=(value:string)=>LABELS[value]||value;

export default function VisaCoordination(){
 const [cases,setCases]=useState<CaseRow[]>([]),[id,setId]=useState(''),[role,setRole]=useState('');
 const [rows,setRows]=useState<Visa[]>([]),[origin,setOrigin]=useState('AF');
 const [departure,setDeparture]=useState(''),[due,setDue]=useState('');
 const [reference,setReference]=useState(''),[authority,setAuthority]=useState(''),[outcome,setOutcome]=useState('issued_reported');
 const [events,setEvents]=useState<Record<string,Event[]>>({});
 const [notice,setNotice]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function load(caseId:string){
  if(!caseId){setRows([]);return;}
  const response=await request<{items:Visa[]}>(ROOT+'/cases/'+encodeURIComponent(caseId)+'/applications');
  setRows(response.items);
 }
 useEffect(()=>{(async()=>{
  const [me,cs]=await Promise.all([request<{role:string}>('/auth/me'),request<CaseRow[]>('/cases?limit=200')]);
  setRole(me.role);setCases(cs);setId(cs[0]?.id||'');
  if(cs[0])await load(cs[0].id);
 })().catch(e=>setError((e as Error).message));},[]);
 async function send(path:string,body:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method:'POST',body:JSON.stringify(body)});
   setNotice('گزارش اداری ثبت شد؛ سامانه به مرجع صادرکننده ویزا متصل نیست.');
   await load(id);
  }catch(e){setError((e as Error).message)}finally{setBusy(false);}
 }
 function act(visaId:string,action:string,other:object={}){
  if(reference.length<6){setError('مرجع اداری غیرحساس حداقل ۶ نویسه لازم است.');return;}
  void send(ROOT+'/applications/'+encodeURIComponent(visaId)+'/transition',{
   step_key:'STEP-'+crypto.randomUUID(),action,reference,...other
  });
 }
 async function showHistory(visaId:string){
  try{
   const result=await request<{items:Event[]}>(ROOT+'/applications/'+encodeURIComponent(visaId)+'/history');
   setEvents(old=>({...old,[visaId]:result.items}));
  }catch(e){setError((e as Error).message);}
 }
 return <Shell title="هماهنگی ویزای درمانی">
  <div className="infoBanner">
   فقط داده ساختگی در محیط توسعه. هیچ درخواست ویزا به مرجع دولتی ارسال نمی‌شود؛ نتیجه‌های ثبت‌شده، گزارش انسانی و غیرقابل اتکا به‌عنوان تأیید رسمی هستند. شماره گذرنامه، تصویر مدرک، تاریخ تولد و شرح پزشکی را در فیلدهای مرجع وارد نکنید. چک‌لیست نمونه است و الزامات رسمی کشورها نیست.
  </div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20}}>
   <h2>۱. درخواست اداری ویزای درمانی</h2>
   <p>پیش‌نیاز: رضایت فعال بیمار برای «پذیرش اولیه» و «هماهنگی ویزا»؛ رضایت باید جداگانه و با اطلاع بیمار ثبت شود.</p>
   <div style={{display:'grid',gap:10,maxWidth:620}}>
    <label>پرونده<select value={id} onChange={e=>{setId(e.target.value);setEvents({});void load(e.target.value).catch(x=>setError((x as Error).message));}}>
     <option value="">انتخاب پرونده</option>{cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} · {c.status}</option>)}
    </select></label>
    <label>کد دوحرفی کشور مبدأ<input maxLength={2} value={origin} onChange={e=>setOrigin(e.target.value.toUpperCase())}/></label>
    <label>تاریخ پیشنهادی سفر (اختیاری)<input type="datetime-local" value={departure} onChange={e=>setDeparture(e.target.value)}/></label>
    <label>مهلت پیگیری داخلی (اختیاری)<input type="datetime-local" value={due} onChange={e=>setDue(e.target.value)}/></label>
    <button disabled={busy||!id||!/^[A-Z]{2}$/.test(origin)} onClick={()=>void send(
     ROOT+'/cases/'+encodeURIComponent(id)+'/applications',{
      request_key:'VISA-'+crypto.randomUUID(),origin_country:origin,
      destination_country:'IR',visa_type:'medical',
      intended_departure_at:departure?new Date(departure).toISOString():null,
      next_action_due_at:due?new Date(due).toISOString():null
     })}>ایجاد درخواست داخلی (نه درخواست دولتی)</button>
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۲. بررسی مدارک و گردش پرونده</h2>
   <div style={{display:'grid',gap:9,maxWidth:620}}>
    <label>مرجع اداری غیرحساس (لاتین، حداقل ۶ نویسه)<input value={reference} minLength={6} maxLength={100}
     pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" onChange={e=>setReference(e.target.value)}/></label>
    <label>عنوان مرجع دریافت‌کننده (فقط برای گزارش دستی)<input value={authority} maxLength={100}
     placeholder="Synthetic Desk" onChange={e=>setAuthority(e.target.value)}/></label>
    <label>نتیجه اعلام‌شده (تأیید مستقل نشده)<select value={outcome} onChange={e=>setOutcome(e.target.value)}>
     {['issued_reported','refused_reported','additional_information_reported'].map(x=><option key={x} value={x}>{title(x)}</option>)}
    </select></label>
   </div>
   {rows.length===0?<p>درخواست ثبت‌شده‌ای وجود ندارد یا رضایت فعال کافی نیست.</p>:
    rows.map(v=><div key={v.id} style={{borderTop:'1px solid #d4dde7',paddingTop:16,marginTop:16,display:'grid',gap:10}}>
     <strong>پرونده {v.id.slice(0,8)} · {title(v.status)} · {v.origin_country} ← {v.destination_country}</strong>
     <small>تأیید رسمی صدور ویزا: خیر · اتصال دولتی: غیرفعال · آخرین مرجع اعلامی: {v.external_reference||'ندارد'}</small>
     {v.decision_reported&&<p>نتیجه ثبت‌شده: {title(v.decision_reported)} — اعتبارسنجی رسمی نشده است.</p>}
     {v.next_action_due_at&&<p>پیگیری داخلی: {new Date(v.next_action_due_at).toLocaleString('fa-IR')}</p>}
     <div style={{display:'grid',gap:8}}>
      {v.checklist.map(c=><div key={c.item_key} style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
       <span>{title(c.item_key)}: {title(c.status)}</span>
       {(v.status==='requested'||v.status==='in_review')&&<>
        <button disabled={busy} onClick={()=>void send(ROOT+'/applications/'+v.id+'/checklist',{
         item_key:c.item_key,status:'received'
        })}>ثبت دریافت</button>
        <button disabled={busy} onClick={()=>void send(ROOT+'/applications/'+v.id+'/checklist',{
         item_key:c.item_key,status:'needs_update'
        })}>نیازمند اصلاح</button>
        {role==='admin'&&<button disabled={busy||reference.length<6} onClick={()=>void send(
         ROOT+'/applications/'+v.id+'/checklist',{item_key:c.item_key,status:'locally_reviewed',review_reference:reference}
        )}>بازبینی مدیر</button>}
       </>}
      </div>)}
     </div>
     <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
      {v.status==='requested'&&<button disabled={busy||reference.length<6}
       onClick={()=>act(v.id,'start_review')}>شروع بررسی</button>}
      {role==='admin'&&v.status==='in_review'&&<button disabled={busy||reference.length<6}
       onClick={()=>act(v.id,'ready_for_manual_submission')}>آماده‌سازی ارسال دستی</button>}
      {role==='admin'&&v.status==='ready_for_manual_submission'&&<button disabled={busy||reference.length<6||authority.length<6}
       onClick={()=>act(v.id,'record_submission',{authority_name:authority})}>ثبت گزارش ارسال به مرجع</button>}
      {role==='admin'&&v.status==='submission_reported'&&<button disabled={busy||reference.length<6||authority.length<6}
       onClick={()=>act(v.id,'record_outcome',{authority_name:authority,outcome})}>ثبت نتیجه اعلام‌شده</button>}
      {role==='admin'&&['requested','in_review','ready_for_manual_submission','submission_reported'].includes(v.status)&&
       <button disabled={busy||reference.length<6} onClick={()=>act(v.id,'cancel')}>لغو پیگیری داخلی</button>}
      <button disabled={busy} onClick={()=>void showHistory(v.id)}>نمایش تاریخچه</button>
     </div>
     {events[v.id]&&<div style={{borderTop:'1px solid #d4dde7',paddingTop:8}}>
      {events[v.id].map(e=><p key={e.id}>{new Date(e.at).toLocaleString('fa-IR')} · {e.action} · {title(e.previous)} → {title(e.current)} · {e.reference}</p>)}
     </div>}
    </div>)}
  </section>
 </Shell>;
}
