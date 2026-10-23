'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Directory={
 physician_id:string;name:string;specialty:string;city:string;
 directory_status:string;evidence_status:string;evidence_expiry:string|null;
 linked_user_id:string|null;hospital_ids:string[];
 regulator_licensure_verified:boolean;
};
type Staff={id:string;email:string;role:string;active:boolean};
type Hospital={id:string;name:string;city:string};
const ROOT='/physician-management';

export default function PhysicianAdministration(){
 const [role,setRole]=useState('');
 const [items,setItems]=useState<Directory[]>([]);
 const [users,setUsers]=useState<Staff[]>([]);
 const [hospitals,setHospitals]=useState<Hospital[]>([]);
 const [doctor,setDoctor]=useState('');
 const [staffId,setStaffId]=useState('');
 const [hospitalId,setHospitalId]=useState('');
 const [country,setCountry]=useState('IR');
 const [authority,setAuthority]=useState('');
 const [licenseReference,setLicenseReference]=useState('');
 const [expires,setExpires]=useState('');
 const [startsAt,setStartsAt]=useState('');
 const [endsAt,setEndsAt]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [loading,setLoading]=useState(true);
 async function load(){
  const [directory,people,places]=await Promise.all([
   request<{items:Directory[]}>(ROOT+'/directory'),
   request<Staff[]>('/staff'),
   request<Hospital[]>('/hospitals'),
  ]);
  setItems(directory.items);
  setUsers(people.filter(x=>x.role==='physician'&&x.active));
  setHospitals(places);
  setDoctor(x=>x||directory.items[0]?.physician_id||'');
  setStaffId(x=>x||people.find(p=>p.role==='physician'&&p.active)?.id||'');
  setHospitalId(x=>x||places[0]?.id||'');
 }
 useEffect(()=>{
  (async()=>{const me=await request<{role:string}>('/auth/me');
   setRole(me.role);if(me.role==='admin')await load();
  })().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 async function action(path:string,method:'PUT'|'POST',payload?:object){
  setBusy(true);setError('');setNotice('');
  try{
   const result=await request<Record<string,unknown>>(path,{method,
    ...(payload?{body:JSON.stringify(payload)}:{})});
   setNotice('عملیات اداری ثبت شد. وضعیت مجوز پزشکی یا تأیید بیرونی تغییر نکرده است.');
   await load();return result;
  }catch(e){setError((e as Error).message)}
  finally{setBusy(false)}
 }
 const chosen=items.find(p=>p.physician_id===doctor);
 return <Shell title="مدیریت پروفایل و دسترسی پزشکان">
  <div className="infoBanner">
   فقط داده‌های ساختگی. تأیید محلی شواهد مجوز، ارتباط بیمارستان یا حضور پیشنهادی، به معنی تأیید توسط نظام پزشکی، مجوز کار بالینی یا نوبت واقعی نیست. دسترسی مستقل پزشک تنها پس از ثبت حساب متصل و مدرک محلی معتبر امکان‌پذیر است.
  </div>
  {loading&&<p>در حال بارگذاری...</p>}
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {notice&&<p className="infoBanner" role="status">{notice}</p>}
  {!loading&&role!=='admin'&&<p>تغییر پروفایل پزشکان فقط با نقش مدیر سازمان مجاز است.</p>}
  {role==='admin'&&<>
   <section className="panel" style={{padding:20}}>
    <div className="panelHeader"><h2>فهرست و انتخاب پزشک</h2>
     <Link href="/providers">ثبت پزشک جدید در فهرست</Link></div>
    <label>پزشک آزمایشی
     <select value={doctor} onChange={e=>setDoctor(e.target.value)}
      style={{display:'block',width:'100%',padding:10}}>
      <option value="">انتخاب پروفایل</option>
      {items.map(x=><option key={x.physician_id} value={x.physician_id}>
       {x.name} — {x.specialty} ({x.city})
      </option>)}
     </select>
    </label>
    {chosen&&<p>
     وضعیت فهرست: {chosen.directory_status} · شواهد مجوز: <strong>{chosen.evidence_status}</strong>
     {chosen.evidence_expiry?' · تاریخ انقضا: '+new Date(chosen.evidence_expiry).toLocaleDateString('fa-IR'):''}
     {' · '}حساب متصل: {chosen.linked_user_id?.slice(0,12)||'ندارد'}
    </p>}
    <p>شمار پزشکان در محدوده: {items.length} · احراز مستقل مجوز توسط مرجع تخصصی: خیر</p>
   </section>
   <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(300px,1fr))',gap:16,marginTop:16}}>
    <section className="panel" style={{padding:20}}>
     <h2>اتصال حساب پزشک</h2>
     <p>ابتدا از صفحه کاربران، حسابی با نقش physician بسازید.</p>
     <label>حساب فعال
      <select value={staffId} onChange={e=>setStaffId(e.target.value)}
       style={{width:'100%',padding:10}}>
       <option value="">انتخاب حساب</option>
       {users.map(x=><option key={x.id} value={x.id}>{x.email}</option>)}
      </select>
     </label>
     <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:12}}>
      <button disabled={busy||!doctor||!staffId}
       onClick={()=>void action(ROOT+'/physicians/'+encodeURIComponent(doctor)+'/account',
        'PUT',{user_id:staffId})}>ثبت ارتباط حساب</button>
      <button disabled={busy||!doctor||!chosen?.linked_user_id}
       onClick={()=>{if(window.confirm('دسترسی این پزشک به پرتال غیرفعال شود؟'))
        void action(ROOT+'/physicians/'+encodeURIComponent(doctor)+'/account/revoke','POST')}}
      >لغو دسترسی پرتال</button>
     </div>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>شواهد بررسی محلی مجوز</h2>
     <form onSubmit={e=>{e.preventDefault();void action(ROOT+'/physicians/'+encodeURIComponent(doctor)+'/credential',
      'PUT',{issuing_country:country,issuing_authority:authority,
       license_reference:licenseReference,expires_at:new Date(expires).toISOString()})}}
      style={{display:'grid',gap:10}}>
      <label>کشور مرجع <input required pattern="[A-Z]{2}" maxLength={2}
       value={country} onChange={e=>setCountry(e.target.value.toUpperCase())}/></label>
      <label>مرجع صادرکننده <input required minLength={3} maxLength={120}
       value={authority} onChange={e=>setAuthority(e.target.value)}/></label>
      <label>شناسه مدرک (بدون متن پزشکی) <input required minLength={6} maxLength={100}
       pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}"
       value={licenseReference} onChange={e=>setLicenseReference(e.target.value)}/></label>
      <label>انقضا (با ساعت محل) <input required type="datetime-local"
       value={expires} onChange={e=>setExpires(e.target.value)}/></label>
      <button disabled={busy||!doctor}>ثبت بررسی محلی</button>
     </form>
     <button style={{marginTop:10}} disabled={busy||!doctor}
      onClick={()=>{if(window.confirm('شواهد این پزشک لغو شوند؟'))
       void action(ROOT+'/physicians/'+encodeURIComponent(doctor)+'/credential/revoke','POST')}}
     >لغو شواهد مدرک</button>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>ارتباط اداری با بیمارستان</h2>
     <label>بیمارستان
      <select value={hospitalId} onChange={e=>setHospitalId(e.target.value)}
       style={{width:'100%',padding:10}}>
       <option value="">انتخاب</option>
       {hospitals.map(x=><option key={x.id} value={x.id}>{x.name} — {x.city}</option>)}
      </select>
     </label>
     <div style={{display:'flex',gap:8,marginTop:12}}>
      <button disabled={busy||!doctor||!hospitalId} onClick={()=>void action(
       ROOT+'/physicians/'+encodeURIComponent(doctor)+'/affiliations','POST',{hospital_id:hospitalId}
      )}>ثبت ارتباط محلی</button>
      <button disabled={busy||!doctor||!hospitalId}
       onClick={()=>{if(window.confirm('ارتباط اداری حذف شود؟'))
        void action(ROOT+'/physicians/'+encodeURIComponent(doctor)+'/affiliations/'+encodeURIComponent(hospitalId)+'/revoke','POST')}}
      >لغو ارتباط</button>
     </div>
     <p>هیچ بیمارستانی تأیید اشتغال واقعی پزشک را از این مسیر اعلام نمی‌کند.</p>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>زمان‌های پیشنهادی حضور</h2>
     <form onSubmit={e=>{e.preventDefault();void action(
      ROOT+'/physicians/'+encodeURIComponent(doctor)+'/availability',
      'POST',{starts_at:new Date(startsAt).toISOString(),
       ends_at:new Date(endsAt).toISOString()})}}
      style={{display:'grid',gap:10}}>
      <label>شروع <input required type="datetime-local" value={startsAt}
       onChange={e=>setStartsAt(e.target.value)}/></label>
      <label>پایان <input required type="datetime-local" value={endsAt}
       onChange={e=>setEndsAt(e.target.value)}/></label>
      <button disabled={busy||!doctor}>ثبت بازه پیشنهادی</button>
     </form>
     <p>این بازه رزرو نیست و به تقویم واقعی پزشک یا بیمارستان متصل نیست.</p>
    </section>
   </div>
  </>}
 </Shell>;
}
