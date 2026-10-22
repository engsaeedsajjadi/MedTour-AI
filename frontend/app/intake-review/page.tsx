'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Item = {
 id:string; case_id:string;language:string;status:string;
 stage:number;questions_total:number;remaining_questions:number;
 urgency_keyword_alert:boolean;clinical_validation:string;
};
type Queue={items:Item[];scan_bounded:boolean;no_phi_returned:boolean};
const statusLabels:Record<string,string>={
 awaiting_clinician_review:'پرسش‌نامه ارسال شده؛ در انتظار بازبینی تخصصی',
 requires_urgent_human_review:'هشدار احتمالی؛ نیازمند ارجاع فوری انسانی',
};
export default function IntakeCoordination(){
 const [items,setItems]=useState<Item[]>([]);
 const [role,setRole]=useState('');
 const [selected,setSelected]=useState('');
 const [action,setAction]=useState<'record_handoff'|'request_more_information'>('request_more_information');
 const [reference,setReference]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [loading,setLoading]=useState(true);
 const active=items.find(x=>x.id===selected);

 async function refresh(){
  const [queue,me]=await Promise.all([
   request<Queue>('/intake-coordination/queue'),
   request<{role:string}>('/auth/me'),
  ]);
  setItems(queue.items);setRole(me.role);setSelected(old=>queue.items.some(x=>x.id===old)?old:(queue.items[0]?.id||''));
 }
 useEffect(()=>{
  refresh().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 },[]);
 async function submit(e:React.FormEvent){
  e.preventDefault();if(!selected)return;
  setBusy(true);setError('');setNotice('');
  try{
   await request('/intake-coordination/sessions/'+encodeURIComponent(selected)+'/review',{
    method:'POST',
    body:JSON.stringify({action,reference:reference.trim()}),
   });
   setNotice(action==='record_handoff'
    ?'تحویل اداری پرونده ثبت شد؛ تأیید بالینی یا پزشکی انجام نشده است.'
    :'درخواست اطلاعات بیشتر ثبت شد؛ بیمار می‌تواند فرم جدید را تکمیل کند.');
   setReference('');await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Shell title="پذیرش اولیه پزشکی">
  <div className="infoBanner">
   این پنل صرفاً هماهنگی اداری پذیرش را مدیریت می‌کند و نباید برای تریاژ یا تشخیص استفاده شود. اطلاعات واقعی بیمار و متن بالینی را در فیلد مرجع وارد نکنید.
  </div>
  {error&&<p className="errorBox" role="alert">{error}</p>}
  {notice&&<p className="infoBanner" role="status">{notice}</p>}
  <section className="panel" style={{padding:20}}>
   <h2>صف پذیرش‌های نیازمند پیگیری</h2>
   {loading?<p>در حال دریافت...</p>:items.length===0?<p>در این لحظه پذیرش نیازمند پیگیری در محدوده نمایش داده‌شده وجود ندارد.</p>:<>
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(250px,1fr))',gap:10}}>
     {items.map(x=><button key={x.id} type="button" onClick={()=>setSelected(x.id)}
      style={{textAlign:'right',border:'1px solid #cbd5df',borderRadius:9,padding:14,background:selected===x.id?'#e2f5f2':'transparent',color:'inherit'}}>
      <strong>پرونده {x.case_id.slice(0,8)}…</strong>
      <p>{statusLabels[x.status]||x.status}</p>
      <small>زبان: {x.language} | مرحله: {x.stage}/{x.questions_total}</small>
     </button>)}
    </div>
    {active&&<div style={{marginTop:18,borderTop:'1px solid #cbd5df',paddingTop:18}}>
     <p>وضعیت: <strong>{statusLabels[active.status]||active.status}</strong></p>
     <p>اعتبارسنجی بالینی: <strong>انجام نشده</strong></p>
     {active.urgency_keyword_alert?<div className="errorBox" role="alert">
      هشدار احتمالی اورژانس: با خدمات اورژانس محلی و متخصص واجد صلاحیت هماهنگ شود. رفع این هشدار از مسیر اداری مجاز نیست.
     </div>:<form onSubmit={submit} style={{maxWidth:580,display:'grid',gap:12}}>
      <label>اقدام اداری
       <select style={{width:'100%',padding:10}} value={action} onChange={e=>setAction(e.target.value as typeof action)}>
        <option value="request_more_information">درخواست تکمیل اطلاعات</option>
        {role==='admin'&&<option value="record_handoff">ثبت تحویل اداری به بازبین</option>}
       </select>
      </label>
      <label>شناسه مرجع اداری، بدون نام یا اطلاعات پزشکی (۶ تا ۱۰۰ کاراکتر)
       <input style={{width:'100%',padding:10}} required minLength={6} maxLength={100}
        pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}" value={reference}
        onChange={e=>setReference(e.target.value)}/>
      </label>
      <button className="button" disabled={busy}>{busy?'در حال ثبت...':'ثبت اقدام و سابقه'}</button>
     </form>}
    </div>}
   </>}
  </section>
 </Shell>;
}
