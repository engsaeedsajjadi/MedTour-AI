'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Hospital={hospital_id:string;name:string;city:string;legacy_directory_status:string;
 evidence_status:string;evidence_expiry:string|null;linked_user_ids:string[];
 service_codes:string[];regulator_license_verified:boolean};
type Staff={id:string;email:string;role:string;active:boolean};
type Case={id:string;status:string;patient_id:string};
type Coord={id:string;status:string;booking_confirmed:boolean};
const ROOT='/hospital-management';
const SERVICES=['cardiology','oncology','orthopedics','ophthalmology','dentistry','neurosurgery','diagnostics','rehabilitation','hospital_admission','other'];
export default function HospitalManagement(){
 const [items,setItems]=useState<Hospital[]>([]);
 const [users,setUsers]=useState<Staff[]>([]);
 const [cases,setCases]=useState<Case[]>([]);
 const [hospital,setHospital]=useState(''),[staff,setStaff]=useState('');
 const [country,setCountry]=useState('IR'),[authority,setAuthority]=useState('');
 const [reg,setReg]=useState(''),[expires,setExpires]=useState('');
 const [service,setService]=useState('cardiology'),[start,setStart]=useState(''),[end,setEnd]=useState('');
 const [units,setUnits]=useState(1),[caseId,setCaseId]=useState(''),[reference,setReference]=useState('');
 const [role,setRole]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [error,setError]=useState(''),[notice,setNotice]=useState('');
 async function reload(){
  const [directory,people,caseList]=await Promise.all([
   request<{items:Hospital[]}>(ROOT+'/directory'),
   request<Staff[]>('/staff'),
   request<Case[]>('/cases?limit=200')
  ]);
  setItems(directory.items);setUsers(people.filter(x=>x.role==='hospital'&&x.active));
  setCases(caseList);setHospital(p=>p||directory.items[0]?.hospital_id||'');
  setStaff(p=>p||people.find(x=>x.role==='hospital'&&x.active)?.id||'');
  setCaseId(p=>p||caseList[0]?.id||'');
 }
 useEffect(()=>{(async()=>{
  const me=await request<{role:string}>('/auth/me');setRole(me.role);
  if(me.role==='admin')await reload();
 })().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));},[]);
 async function doAction(path:string,method:'PUT'|'POST',payload?:object){
  setBusy(true);setError('');setNotice('');
  try{
   const result=await request<Coord>(path,{method,...(payload?{body:JSON.stringify(payload)}:{})});
   setNotice('رویداد اداری ثبت شد؛ مجوز، ظرفیت یا رزرو بیرونی تأیید نشده است. شناسه: '+(result.id?.slice(0,10)||'ثبت شد'));
   await reload();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const chosen=items.find(x=>x.hospital_id===hospital);
 return <Shell title="مدیریت سازمانی بیمارستان‌ها">
  <div className="infoBanner">فقط داده ساختگی. ثبت مدرک، خدمات و ظرفیت پیشنهادی اثبات مجوز بیمارستان، ظرفیت واقعی یا پذیرش پزشکی نیست. درخواست داخلی به‌معنی ارسال پیام به بیمارستان یا رزرو تخت نیست.</div>
  {loading&&<p>در حال بررسی نقش و بیمارستان‌ها...</p>}
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {notice&&<p className="infoBanner" role="status">{notice}</p>}
  {!loading&&role!=='admin'&&<p>مدیریت بیمارستان فقط برای مدیر سازمان است.</p>}
  {role==='admin'&&<>
   <section className="panel" style={{padding:20}}>
    <h2>فهرست مراکز و وضعیت مدارک</h2>
    <Link href="/hospitals">افزودن بیمارستان آزمایشی</Link>
    <label>مرکز
     <select value={hospital} onChange={e=>setHospital(e.target.value)} style={{display:'block',padding:10,width:'100%'}}>
      <option value="">انتخاب مرکز</option>
      {items.map(x=><option key={x.hospital_id} value={x.hospital_id}>{x.name} — {x.city}</option>)}
     </select>
    </label>
    {chosen&&<p>وضعیت قدیمی فهرست: {chosen.legacy_directory_status} · شواهد محلی: <strong>{chosen.evidence_status}</strong> ·
     خدمات ثبت‌شده: {chosen.service_codes.join(', ')||'بدون خدمت'} · حساب‌های فعال: {chosen.linked_user_ids.length}</p>}
    <p>تأیید مستقل نهاد صادرکننده مجوز: <strong>انجام نشده</strong></p>
   </section>
   <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(310px,1fr))',gap:16,marginTop:16}}>
    <section className="panel" style={{padding:20}}>
     <h2>حساب پرتال بیمارستان</h2>
     <p>ابتدا از <Link href="/staff">صفحه کاربران</Link>، حسابی با نقش hospital بسازید.</p>
     <label>حساب کاربر
      <select value={staff} onChange={e=>setStaff(e.target.value)} style={{width:'100%',padding:10}}>
       <option value="">انتخاب</option>{users.map(x=><option value={x.id} key={x.id}>{x.email}</option>)}
      </select>
     </label>
     <div style={{display:'flex',gap:8,marginTop:10}}>
      <button disabled={busy||!hospital||!staff} onClick={()=>void doAction(ROOT+'/hospitals/'+hospital+'/accounts','PUT',{user_id:staff})}>متصل کردن</button>
      <button disabled={busy||!hospital||!staff} onClick={()=>{
       if(window.confirm('دسترسی پرتال این کاربر لغو شود؟'))
        void doAction(ROOT+'/hospitals/'+hospital+'/accounts/'+staff+'/revoke','POST');
      }}>لغو دسترسی</button>
     </div>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>شواهد بررسی محلی مجوز</h2>
     <form onSubmit={e=>{e.preventDefault();void doAction(ROOT+'/hospitals/'+hospital+'/credential','PUT',{
      issuing_country:country,issuing_authority:authority,registration_reference:reg,
      expires_at:new Date(expires).toISOString()})}} style={{display:'grid',gap:9}}>
      <label>کشور <input required pattern="[A-Z]{2}" maxLength={2} value={country} onChange={e=>setCountry(e.target.value.toUpperCase())}/></label>
      <label>مرجع صادرکننده <input required minLength={3} maxLength={120} value={authority} onChange={e=>setAuthority(e.target.value)}/></label>
      <label>مرجع بررسی غیرحساس <input required minLength={6} maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" value={reg} onChange={e=>setReg(e.target.value)}/></label>
      <label>انقضا <input required type="datetime-local" value={expires} onChange={e=>setExpires(e.target.value)}/></label>
      <button disabled={busy||!hospital}>ثبت شواهد محلی</button>
     </form>
     <button style={{marginTop:9}} disabled={busy||!hospital} onClick={()=>{
      if(window.confirm('مدرک ثبت‌شده محلی لغو شود؟'))void doAction(ROOT+'/hospitals/'+hospital+'/credential/revoke','POST');
     }}>لغو مدرک</button>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>کاتالوگ خدمات اداری</h2>
     <label>خدمت<select value={service} onChange={e=>setService(e.target.value)} style={{display:'block',padding:10,width:'100%'}}>
      {SERVICES.map(s=><option key={s} value={s}>{s}</option>)}
     </select></label>
     <div style={{display:'flex',gap:8,marginTop:9}}>
      <button disabled={busy||!hospital} onClick={()=>void doAction(ROOT+'/hospitals/'+hospital+'/services','POST',{service_code:service})}>ثبت خدمت</button>
      <button disabled={busy||!hospital} onClick={()=>{
       if(window.confirm('خدمت از فهرست داخلی لغو شود؟'))
        void doAction(ROOT+'/hospitals/'+hospital+'/services/'+service+'/revoke','POST');
      }}>لغو خدمت</button>
     </div>
     <p>هیچ خدمت ثبت‌شده‌ای به‌صورت مستقل توسط بیمارستان تأیید نشده است.</p>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>ظرفیت پیشنهادی، نه قابل رزرو</h2>
     <form onSubmit={e=>{e.preventDefault();void doAction(ROOT+'/hospitals/'+hospital+'/capacity','POST',{
      service_code:service,starts_at:new Date(start).toISOString(),ends_at:new Date(end).toISOString(),proposed_units:units
     })}} style={{display:'grid',gap:9}}>
      <label>شروع <input required type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label>پایان <input required type="datetime-local" value={end} onChange={e=>setEnd(e.target.value)}/></label>
      <label>تعداد واحد پیشنهادی <input required type="number" min={1} max={100} value={units} onChange={e=>setUnits(Number(e.target.value))}/></label>
      <button disabled={busy||!hospital}>ثبت ظرفیت پیشنهادی</button>
     </form>
    </section>
   </div>
   <section className="panel" style={{padding:20,marginTop:16}}>
    <h2>درخواست هماهنگی با مرکز</h2>
    <p>ثبت این درخواست به دو رضایت فعال intake و hospital_coordination نیاز دارد. مرجع اداری نباید داده پزشکی داشته باشد.</p>
    <form onSubmit={e=>{e.preventDefault();void doAction(ROOT+'/hospitals/'+hospital+'/coordinations','POST',{
     case_id:caseId,service_code:service,reference})}} style={{display:'grid',gap:9,maxWidth:610}}>
     <label>پرونده<select required value={caseId} onChange={e=>setCaseId(e.target.value)} style={{width:'100%',padding:10}}>
      <option value="">انتخاب پرونده</option>{cases.map(x=><option value={x.id} key={x.id}>{x.id.slice(0,8)} — {x.status}</option>)}
     </select></label>
     <label>شناسه مرجع اداری <input required minLength={6} maxLength={100} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" value={reference} onChange={e=>setReference(e.target.value)}/></label>
     <button disabled={busy||!hospital||!caseId}>ثبت درخواست بدون ارسال پیام</button>
    </form>
    <p><Link href="/hospital-workspace">نمای محدود کارکنان بیمارستان</Link></p>
   </section>
  </>}
 </Shell>;
}
