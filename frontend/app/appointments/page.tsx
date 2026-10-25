'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
type Case={id:string;status:string;specialty:string};
type Doctor={id:string;full_name:string;specialty:string};
type Booking={id:string;physician_id:string;starts_at:string;ends_at:string;status:string;external_booking_confirmed:boolean};
export default function Appointments(){
 const [cases,setCases]=useState<Case[]>([]),[doctors,setDoctors]=useState<Doctor[]>([]);
 const [id,setId]=useState(''),[doctor,setDoctor]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState('');
 const [rows,setRows]=useState<Booking[]>([]),[ref,setRef]=useState(''),[role,setRole]=useState('');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 async function load(caseId:string){
  if(!caseId)return;
  const res=await request<{items:Booking[]}>('/appointment-calendar/cases/'+encodeURIComponent(caseId));
  setRows(res.items);
 }
 useEffect(()=>{(async()=>{
  const [me,cs,ds]=await Promise.all([request<{role:string}>('/auth/me'),request<Case[]>('/cases?limit=200'),request<Doctor[]>('/physicians')]);
  setRole(me.role);setCases(cs);setDoctors(ds);setId(cs[0]?.id||'');setDoctor(ds[0]?.id||'');
  if(cs[0])await load(cs[0].id);
 })().catch(e=>setError((e as Error).message))},[]);
 async function act(path:string,body:object){
  setBusy(true);setError('');setNotice('');
  try{await request(path,{method:'POST',body:JSON.stringify(body)});
   setNotice('در تقویم داخلی ثبت شد؛ هیچ رزرو خارجی یا تأیید پزشکی ایجاد نشده است.');
   await load(id);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="تقویم و مدیریت نوبت‌های اداری">
  <div className="infoBanner">فقط محیط توسعه با داده ساختگی. پیش‌نیاز: ظرفیت پیشنهادی در مدیریت پزشکان ثبت شده باشد. زمان‌ها بر اساس منطقه زمانی مرورگر وارد و به UTC تبدیل می‌شوند. تأیید داخلی به معنی تأیید نوبت از پزشک یا بیمارستان نیست.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20}}>
   <h2>درخواست بازه پیشنهادی</h2>
   <div style={{display:'grid',gap:12,maxWidth:640}}>
    <label>پرونده<select value={id} onChange={e=>{setId(e.target.value);void load(e.target.value).catch(x=>setError((x as Error).message))}}>
     <option value="">انتخاب پرونده</option>{cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.specialty}</option>)}
    </select></label>
    <label>پزشک<select value={doctor} onChange={e=>setDoctor(e.target.value)}>
     <option value="">انتخاب پزشک</option>{doctors.map(d=><option key={d.id} value={d.id}>{d.full_name} — {d.specialty}</option>)}
    </select></label>
    <label>شروع<input required type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label>
    <label>پایان<input required type="datetime-local" value={end} onChange={e=>setEnd(e.target.value)}/></label>
    <button disabled={busy||!id||!doctor||!start||!end} onClick={()=>void act('/appointment-calendar/requests',{
     case_id:id,physician_id:doctor,starts_at:new Date(start).toISOString(),ends_at:new Date(end).toISOString(),
     request_key:'APPT-'+crypto.randomUUID()
    })}>ثبت درخواست با کنترل تداخل</button>
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>نوبت‌های ثبت‌شده در سیستم داخلی</h2>
   <label>مرجع اداری بازبینی <input minLength={6} maxLength={100} value={ref} onChange={e=>setRef(e.target.value)}/></label>
   {rows.map(x=><div key={x.id} style={{padding:12,borderBottom:'1px solid #ddd'}}>
    <p>پزشک {x.physician_id.slice(0,8)} · {new Date(x.starts_at).toLocaleString('fa-IR')} — {new Date(x.ends_at).toLocaleString('fa-IR')} · {x.status}</p>
    {role==='admin'&&x.status==='requested'&&<div style={{display:'flex',gap:8}}>
     <button disabled={busy||ref.length<6} onClick={()=>void act('/appointment-calendar/requests/'+x.id+'/review',{action:'internally_confirmed',reference:ref})}>تأیید داخلی</button>
     <button disabled={busy||ref.length<6} onClick={()=>void act('/appointment-calendar/requests/'+x.id+'/review',{action:'cancelled',reference:ref})}>لغو</button>
    </div>}
    <small>وضعیت رزرو خارجی: تأیید نشده</small>
   </div>)}
  </section>
 </Shell>;
}
