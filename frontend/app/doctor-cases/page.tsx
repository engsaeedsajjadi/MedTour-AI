'use client';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {useEffect,useState} from 'react';
type Case={id:string;specialty:string;status:string};
export default function DoctorCases(){
 const [cases,setCases]=useState<Case[]>([]);
 const [error,setError]=useState('');
 useEffect(()=>{request<{items:Case[]}>('/identity/doctor/cases').then(x=>setCases(x.items)).catch(e=>setError((e as Error).message));},[]);
 return <Shell title="پرونده‌های ارجاع‌شده پزشک">
  <div className="infoBanner">دسترسی پزشک در این نسخه صرفاً فهرست وضعیت اداری پرونده‌هایی است که مدیر همان سازمان اختصاص داده است. مدارک پزشکی، اطلاعات هویتی بیمار و تصمیم بالینی در این صفحه ارائه نمی‌شود. صلاحیت حرفه‌ای پزشک هنوز مستقل اعتبارسنجی نشده است.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>پرونده‌های مجاز</h2>
   {cases.length===0?<p>هنوز پرونده مجازی به این حساب اختصاص داده نشده است.</p>:
    <div className="tableScroll"><table><thead><tr><th>شناسه پرونده</th><th>تخصص</th><th>وضعیت</th></tr></thead><tbody>{cases.map(x=><tr key={x.id}><td dir="ltr">{x.id.slice(0,12)}…</td><td>{x.specialty||'ثبت نشده'}</td><td>{x.status}</td></tr>)}</tbody></table></div>}
  </section>
 </Shell>;
}
