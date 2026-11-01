'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {fa,fmtDateTime,fmtDate} from '@/lib/i18n';

type Me={
 physician_id:string;name:string;specialty:string;city:string;
 directory_status:string;evidence_status:string;evidence_expiry:string|null;
 hospital_ids:string[];regulator_licensure_verified:boolean;
};
type Referral={id:string;case_reference:string;status:string;created_at:string};
type Appointment={id:string;case_reference:string;status:string;requested_at:string};
type Availability={id:string;starts_at:string;ends_at:string;status:string};
export default function PhysicianWorkspace(){
 const [me,setMe]=useState<Me|null>(null);
 const [referrals,setReferrals]=useState<Referral[]>([]);
 const [appointments,setAppointments]=useState<Appointment[]>([]);
 const [slots,setSlots]=useState<Availability[]>([]);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 useEffect(()=>{
  (async()=>{
   const [identity,refs,appts,available]=await Promise.all([
    request<Me>('/physician-management/portal/me'),
    request<{items:Referral[]}>('/physician-management/portal/referrals'),
    request<{items:Appointment[]}>('/physician-management/portal/appointments'),
    request<{items:Availability[]}>('/physician-management/portal/availability'),
   ]);
   setMe(identity);setReferrals(refs.items);setAppointments(appts.items);setSlots(available.items);
  })().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 return <Shell title="پرتال اختصاصی پزشک">
  <div className="infoBanner">در این پرتال ارجاع‌ها و درخواست‌های نوبت مربوط به شما نمایش داده می‌شود. مدارک و اطلاعات تماس بیماران از مسیر جداگانه و با رضایت بیمار در اختیار شما قرار می‌گیرد.</div>
  {loading&&<p>در حال بررسی ارتباط حساب و اعتبار شواهد...</p>}
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {me&&<>
   <section className="panel" style={{padding:20}}>
    <h2>{me.name}</h2>
    <p>تخصص: {me.specialty} · شهر: {me.city}</p>
    <p>وضعیت فهرست: {me.directory_status} · وضعیت بررسی محلی مدرک: {fa(me.evidence_status)}</p>
    <p>انقضای شواهد: {me.evidence_expiry?fmtDate(me.evidence_expiry):'نامشخص'}</p>
    <p>استعلام مستقل مجوز: <strong>انجام نشده</strong></p>
    <p>درخواست بازبینی فرم پذیرش فقط از طریق <Link href="/intake-clinician">مسیر بازبینی انسانی محدود</Link> انجام می‌شود که کنترل مجوز و انتساب جداگانه دارد.</p>
   </section>
   <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(320px,1fr))',gap:16,marginTop:16}}>
    <section className="panel" style={{padding:20}}>
     <h2>ارجاع‌های مختص پزشک</h2>
     {referrals.length===0?<p>ارجاعی موجود نیست.</p>:referrals.map(x=><div key={x.id} style={{padding:9,borderBottom:'1px solid #d7dfe5'}}>
      <strong>کد ارجاع {x.id.slice(0,12)}</strong>
      <p>پرونده اداری {x.case_reference.slice(0,10)} · وضعیت: {fa(x.status)}</p>
     </div>)}
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>درخواست‌های نوبت</h2>
     {appointments.length===0?<p>درخواستی موجود نیست.</p>:appointments.map(x=><div key={x.id} style={{padding:9,borderBottom:'1px solid #d7dfe5'}}>
      <strong>{fmtDateTime(x.requested_at)}</strong>
      <p>وضعیت داخلی: {fa(x.status)} · شناسه {x.id.slice(0,10)}</p>
     </div>)}
     <p>وضعیت داخلی به معنی تأیید نوبت توسط پزشک یا مرکز درمانی نیست.</p>
    </section>
    <section className="panel" style={{padding:20}}>
     <h2>بازه‌های پیشنهادی</h2>
     {slots.length===0?<p>بازه‌ای ثبت نشده است.</p>:slots.map(x=><p key={x.id}>
      {fmtDateTime(x.starts_at)} تا {fmtDateTime(x.ends_at)} · پیشنهادی
     </p>)}
     <p>این فهرست به‌صورت خودکار با تقویم مطب شما همگام نمی‌شود.</p>
    </section>
   </div>
  </>}
 </Shell>;
}
