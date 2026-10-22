'use client';

import {useCallback, useEffect, useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type CaseRow = {id:string; patient_id:string; specialty:string; status:string};
type Mission = {
 case_id:string;status:string;conditions:Record<string,boolean>;
 signals:{has_staff_conversation:boolean;human_handoff:boolean;
          documents_recorded:number;travel_services_requested:number;
          travel_services_unresolved:boolean;urgent_intake_detected:boolean};
 required_for_status:Record<string,string[]>;note:string;
};
type HistoryRow = {id:string;current_status:string;evidence_reference:string;created_at:string};
const LABELS:Record<string,string>={
 intake_consent:'رضایت پذیرش',communication_consent:'رضایت ارتباطات',
 intake_submitted:'پرسش‌نامه کامل (نیازمند بازبینی)',emergency_clear:'عدم هشدار اورژانسی ثبت‌شده',
 referral_approved:'ارجاع بازبینی‌شده به پزشک تأییدشده',quote_approved:'پیش‌فاکتور مصوب',
 appointment_confirmed:'نوبت تأییدشده با مرجع مستقل',travel_resolved:'درخواست‌های سفر تعیین‌تکلیف‌شده',
 followup_recorded:'پیگیری تأییدشده با مرجع ثبت‌شده'
};
const NEXT:Record<string,string[]>={
 new:['intake','cancelled'],intake:['documents_pending','review_pending','cancelled'],
 documents_pending:['review_pending','cancelled'],review_pending:['provider_review','cancelled'],
 provider_review:['quote_pending','cancelled'],quote_pending:['quote_sent','cancelled'],
 quote_sent:['confirmed','quote_pending','cancelled'],
 confirmed:['travel_planning','cancelled'],travel_planning:['arrived','cancelled'],
 arrived:['in_treatment','cancelled'],in_treatment:['follow_up'],follow_up:['closed']
};
const EVIDENCE=new Set(['confirmed','arrived','in_treatment','follow_up','closed']);

export default function JourneyOperations() {
 const [cases,setCases]=useState<CaseRow[]>([]);
 const [selected,setSelected]=useState('');
 const [mission,setMission]=useState<Mission|null>(null);
 const [history,setHistory]=useState<HistoryRow[]>([]);
 const [target,setTarget]=useState('');
 const [reference,setReference]=useState('');
 const [role,setRole]=useState('');
 const [loading,setLoading]=useState(true);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');

 const loadMission=useCallback(async (id:string)=>{
  const [m,h]=await Promise.all([
   request<Mission>('/cases/'+encodeURIComponent(id)+'/mission'),
   request<HistoryRow[]>('/cases/'+encodeURIComponent(id)+'/mission/history')
  ]);
  setMission(m);setHistory(h);setTarget('');setReference('');
 },[]);
 useEffect(()=>{
  Promise.all([request<CaseRow[]>('/cases'),request<{role:string}>('/auth/me')])
   .then(([rows,u])=>{setCases(rows);setRole(u.role);if(rows.length)setSelected(rows[0].id);})
   .catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 useEffect(()=>{
  if(!selected){setMission(null);setHistory([]);return;}
  setMission(null);setError('');
  loadMission(selected).catch(e=>setError((e as Error).message));
 },[selected,loadMission]);

 async function advance(e:React.FormEvent){
  e.preventDefault();if(!mission||!target)return;
  setError('');setNotice('');setBusy(true);
  try{
   await request('/cases/'+encodeURIComponent(mission.case_id)+'/status',{
    method:'PATCH',body:JSON.stringify({status:target,reference:reference.trim()||null})
   });
   setCases(old=>old.map(c=>c.id===mission.case_id?{...c,status:target}:c));
   await loadMission(mission.case_id);
   setNotice('تغییر مرحله به‌عنوان یک عملیات اداری ثبت شد؛ تأیید خارجی خودکار انجام نشده است.');
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 const missing=(mission&&target?(mission.required_for_status[target]||[]).filter(
  key=>!mission.conditions[key]
 ):[]);
 const needsSupervisor=target&&EVIDENCE.has(target);
 return <Shell title="مسیر عملیاتی پرونده">
  <div className="infoBanner">این صفحه برای هماهنگی اداری در محیط توسعه است؛ تشخیص بالینی، رزرو واقعی، پذیرش بیمارستان یا مجوز ورود را تأیید نمی‌کند. از داده واقعی بیمار استفاده نکنید.</div>
  {error&&<p role="alert" className="errorBox">{error}</p>}
  {notice&&<p role="status" className="infoBanner">{notice}</p>}
  <section className="panel" style={{padding:20}}>
   <h2>انتخاب پرونده</h2>
   {loading?<p>در حال بارگذاری...</p>:cases.length===0?<p>ابتدا یک پرونده آزمایشی بسازید.</p>:<>
    <select aria-label="پرونده" value={selected} onChange={e=>setSelected(e.target.value)}
     style={{width:'100%',padding:10,marginBottom:14}}>
     {cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.specialty||'بدون تخصص'} — {c.status}</option>)}
    </select>
    {!mission?<p>در حال دریافت وضعیت...</p>:<>
     <p><strong>مرحله کنونی:</strong> {mission.status}</p>
     {mission.signals.urgent_intake_detected&&<p role="alert" className="errorBox">هشدار احتمالی اورژانسی در پذیرش ثبت شده است؛ برای ارزیابی فوری به تیم درمان ارجاع دهید.</p>}
     <h3>شواهد موردنیاز</h3>
     <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(230px,1fr))',gap:8,marginBottom:16}}>
      {Object.entries(mission.conditions).map(([key,value])=>
       <div key={key} style={{padding:12,border:'1px solid #d1dae0',borderRadius:8}}>
        <strong>{value?'✓':'–'} {LABELS[key]||key}</strong>
       </div>
      )}
     </div>
     <p>تعداد اسناد ثبت‌شده: {mission.signals.documents_recorded} | درخواست‌های سفر: {mission.signals.travel_services_requested} | انتقال به اپراتور: {mission.signals.human_handoff?'بله':'خیر'}</p>
     <form onSubmit={advance} style={{display:'grid',gap:10,maxWidth:650}}>
      <label>مرحله بعدی
       <select value={target} onChange={e=>{setTarget(e.target.value);setReference('');}}
        style={{display:'block',width:'100%',padding:10}} required>
        <option value="">انتخاب مرحله</option>
        {(NEXT[mission.status]||[]).map(s=><option key={s} value={s}>{s}</option>)}
       </select>
      </label>
      {needsSupervisor&&<label>مرجع تأیید انسانی مدیر (۶ تا ۱۰۰ کاراکتر؛ بدون اطلاعات پزشکی)
       <input style={{display:'block',width:'100%',padding:10}} value={reference}
        onChange={e=>setReference(e.target.value)} minLength={6} maxLength={100}
        pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" required/>
      </label>}
      {!!missing?.length&&<p role="alert" className="errorBox">پیش‌نیازهای ثبت‌نشده: {missing.map(k=>LABELS[k]||k).join('، ')}</p>}
      {needsSupervisor&&role!=='admin'&&<p role="alert">تنها مدیر مجاز به تأیید این مرحله است.</p>}
      <button className="button" type="submit" disabled={busy||!target||!!missing?.length||(!!needsSupervisor&&role!=='admin')}>
       {busy?'در حال ثبت...':'ثبت تغییر مرحله'}
      </button>
     </form>
     <h3 style={{marginTop:20}}>سوابق تغییر مرحله</h3>
     <div className="tableScroll"><table><thead><tr><th>مرحله</th><th>مرجع اداری</th><th>زمان</th></tr></thead>
      <tbody>{history.length===0?<tr><td colSpan={3}>هنوز رویدادی ثبت نشده است.</td></tr>:
       history.map(h=><tr key={h.id}><td>{h.current_status}</td><td>{h.evidence_reference}</td><td>{new Date(h.created_at).toLocaleString('fa-IR')}</td></tr>)}
      </tbody></table></div>
    </>}
   </>}
  </section>
 </Shell>;
}
