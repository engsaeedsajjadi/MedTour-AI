'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {request} from '@/lib/api';

/** Shows a warning only while the real-patient readiness checklist is incomplete (administrators only). */
export default function ReadinessNotice(){
 const [missing,setMissing]=useState<number|null>(null);
 useEffect(()=>{request<{ready_for_real_patients:boolean;checks:{passed:boolean}[]}>('/compliance/readiness')
  .then(r=>setMissing(r.ready_for_real_patients?0:r.checks.filter(c=>!c.passed).length)).catch(()=>setMissing(null));},[]);
 if(!missing)return null;
 return <div className="infoBanner" role="status">چک‌لیست آمادگی عملیاتی هنوز {missing.toLocaleString('fa-IR')} مورد ناتمام دارد. تا تکمیل آن، اطلاعات بیماران واقعی را وارد نکنید. <Link className="textLink" href="/tenant-isolation">مشاهده چک‌لیست</Link></div>;
}
