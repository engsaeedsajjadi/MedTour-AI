'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Profile={hospital_id:string;name:string;city:string;evidence_status:string;
 regulator_license_verified:boolean;hospital_capacity_live_verified:boolean};
type Capacity={id:string;service_code:string;starts_at:string;ends_at:string;proposed_units:number;status:string};
type Coordination={id:string;case_reference:string;service_code:string;status:string;created_at:string;booking_confirmed:boolean};
const ROOT='/hospital-management';
export default function HospitalWorkspace(){
 const [me,setMe]=useState<Profile|null>(null);
 const [slots,setSlots]=useState<Capacity[]>([]);
 const [requests,setRequests]=useState<Coordination[]>([]);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false);
 const [error,setError]=useState(''),[notice,setNotice]=useState('');
 async function refresh(){
  const [p,capacity,requests]=await Promise.all([
   request<Profile>(ROOT+'/portal/me'),
   request<{items:Capacity[]}>(ROOT+'/portal/capacity'),
   request<{items:Coordination[]}>(ROOT+'/portal/coordinations')
  ]);
  setMe(p);setSlots(capacity.items);setRequests(requests.items);
 }
 useEffect(()=>{refresh().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));},[]);
 async function receipt(id:string){
  if(!window.confirm('فقط دریافت اداری درخواست را ثبت می‌کنید. این اقدام رزرو یا تأیید پزشکی نیست.'))return;
  setBusy(true);setError('');setNotice('');
  try{
   await request(ROOT+'/portal/coordinations/'+encodeURIComponent(id)+'/acknowledge',{method:'POST'});
   setNotice('دریافت داخلی درخواست ثبت شد. پذیرش، ظرفیت یا رزرو خارجی تأیید نشده است.');
   await refresh();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="پرتال محدود بیمارستان">
  <div className="infoBanner">فقط محیط آزمایشی با اطلاعات ساختگی. این صفحه صرفاً شناسه‌های اداری درخواست‌های متعلق به همین بیمارستان را نمایش می‌دهد و مجوز دسترسی به مدارک پزشکی، تماس بیمار، پذیرش واقعی یا تأیید رزرو ندارد.</div>
  {loading&&<p>در حال اعتبارسنجی ارتباط حساب و مدرک محلی...</p>}
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {notice&&<p className="infoBanner" role="status">{notice}</p>}
  {me&&<>
   <section className="panel" style={{padding:20}}>
    <h2>{me.name}</h2>
    <p>شهر: {me.city} · وضعیت شواهد محلی: {me.evidence_status}</p>
    <p>تأیید مستقل مجوز: <strong>خیر</strong> · ظرفیت قابل رزرو: <strong>تأیید نشده</strong></p>
   </section>
   <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(320px,1fr))',gap:16,marginTop:16}}>
    <section className="panel" style={{padding:20}}>
     <h2>بازه‌های ظرفیت پیشنهادی</h2>
     {slots.length===0?<p>ظرفیت پیشنهادی فعالی وجود ندارد.</p>:slots.map(x=>
      <p key={x.id}>{x.service_code} · {x.proposed_units} واحد · از {new Date(x.starts_at).toLocaleString('fa-IR')} تا {new Date(x.ends_at).toLocaleString('fa-IR')}</p>)}
     <p>اطلاعات این فهرست به تقویم و ظرفیت واقعی بیمارستان متصل نیست.</p>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>درخواست‌های هماهنگی داخلی</h2>
     {requests.length===0?<p>درخواست مجاز فعالی موجود نیست.</p>:requests.map(x=>
      <div key={x.id} style={{padding:10,borderBottom:'1px solid #d4dde3'}}>
       <strong>پرونده اداری {x.case_reference.slice(0,10)}</strong>
       <p>خدمت: {x.service_code} · وضعیت: {x.status}</p>
       {x.status==='requested'&&<button disabled={busy} onClick={()=>void receipt(x.id)}>ثبت دریافت اداری</button>}
      </div>)}
     <p>ثبت دریافت اداری، به معنی تأیید رزرو، نوبت، پذیرش یا ارسال پیام بیرونی نیست.</p>
    </section>
   </div>
  </>}
 </Shell>;
}
