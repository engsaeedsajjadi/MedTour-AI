'use client';

import Link from 'next/link';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Stats={
 patients:number;cases:number;active_cases:number;staff_active:number;
 cases_by_status:Record<string,number>;overdue_followups:number;
 pending_operations:number;draft_quotes:number;human_handoffs:number;
 urgent_intake_flags:number;pending_translations:number;
 outbound_needs_human_approval:number;external_providers_live_verified:boolean;
 real_patient_data_allowed:boolean;
};
type QueueItem={
 category:string;id:string;case_id:string|null;priority:string;
 status:string;created_at:string;destination:string;automatic_decision:boolean;
};
type Queue={items:QueueItem[];scan_bounded:boolean;total_matches_exhaustive:boolean};
type Result={type:string;id:string;label:string;patient_id:string|null;case_id:string|null;destination:string};
type Staff={id:string;email:string;role:string;active:boolean};
type CaseOverview={case_id:string;patient_id:string;status:string;
 assigned_operator_id:string|null;communication_consent:boolean;
 intake_consent:boolean;open_followups:number;pending_operations:number;
 medical_records_included:boolean};

const tiles:[keyof Stats,string,string][]=[
 ['active_cases','پرونده‌های فعال','/cases'],
 ['overdue_followups','پیگیری‌های معوق','/crm'],
 ['urgent_intake_flags','هشدارهای پذیرش','/intake-review'],
 ['pending_operations','خدمات در انتظار','/operations'],
 ['draft_quotes','پیش‌فاکتورهای پیش‌نویس','/quotations'],
 ['human_handoffs','ارجاع‌های انسانی گفتگو','/conversations'],
];
const categories=[
 ['','همه موارد'],['urgent_intake','هشدار پذیرش'],
 ['review_intake','پذیرش نیازمند بازبینی'],['followup_overdue','پیگیری معوق'],
 ['operation_review','هماهنگی خدمات'],['quote_approval','پیش‌فاکتور'],
 ['human_handoff','گفتگوهای ارجاع‌شده']
] as const;

export default function AdminCenter(){
 const [role,setRole]=useState('');
 const [selfId,setSelfId]=useState('');
 const [summary,setSummary]=useState<Stats|null>(null);
 const [queue,setQueue]=useState<Queue|null>(null);
 const [category,setCategory]=useState('');
 const [domain,setDomain]=useState('all');
 const [term,setTerm]=useState('');
 const [results,setResults]=useState<Result[]>([]);
 const [staff,setStaff]=useState<Staff[]>([]);
 const [target,setTarget]=useState('');
 const [selectedCase,setSelectedCase]=useState('');
 const [overview,setOverview]=useState<CaseOverview|null>(null);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 const [loading,setLoading]=useState(true);

 async function reload(qCategory=category){
  const [stats,q,users]=await Promise.all([
   request<Stats>('/admin-center/summary'),
   request<Queue>('/admin-center/queue?limit=100'+
     (qCategory?'&category='+encodeURIComponent(qCategory):'')),
   request<Staff[]>('/staff'),
  ]);
  setSummary(stats);setQueue(q);setStaff(users);
 }
 useEffect(()=>{
  (async()=>{
   const me=await request<{id:string;role:string}>('/auth/me');
   setRole(me.role);setSelfId(me.id);
   if(me.role==='admin')await reload('');
  })().catch(e=>setError((e as Error).message)).finally(()=>setLoading(false));
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 async function changeCategory(next:string){
  setCategory(next);setError('');
  try{setQueue(await request<Queue>('/admin-center/queue?limit=100'+
   (next?'&category='+encodeURIComponent(next):'')));}
  catch(e){setError((e as Error).message)}
 }
 async function search(e:React.FormEvent){
  e.preventDefault();setError('');setResults([]);
  if(term.trim().length<3)return;
  setBusy(true);
  try{
   const data=await request<{items:Result[]}>(
    '/admin-center/search?q='+encodeURIComponent(term.trim())+
    '&domain='+encodeURIComponent(domain)+'&limit=50');
   setResults(data.items);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function showCase(id:string){
  setSelectedCase(id);setError('');
  try{setOverview(await request<CaseOverview>(
   '/admin-center/cases/'+encodeURIComponent(id)+'/overview'))}
  catch(e){setOverview(null);setError((e as Error).message)}
 }
 async function deactivate(){
  const user=staff.find(x=>x.id===target);
  if(!user||user.id===selfId)return;
  if(!window.confirm('حساب '+user.email+' غیرفعال شود؟ ابتدا تمام پرونده‌ها، گفتگوها و کارهای او باید واگذار شده باشند.'))return;
  setBusy(true);setError('');setNotice('');
  try{
   await request('/admin-center/staff/'+encodeURIComponent(user.id)+'/deactivate',{method:'POST'});
   setNotice('حساب غیرفعال شد؛ نشست‌های آن در درخواست بعدی معتبر نخواهند بود.');
   setTarget('');await reload();
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="مرکز کنترل مدیریتی">
  <div className="infoBanner">این پنل فقط برای مدیر سازمان و داده‌های آزمایشی است. آمار مستقیماً از دیتابیس همان سازمان خوانده می‌شود؛ وضعیت اتصال و تأیید خارجی خدمات از آن استنباط نمی‌شود. متن پزشکی و فایل بیمار در جستجو یا صف نمایش داده نمی‌شوند.</div>
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {notice&&<div role="status" className="infoBanner">{notice}</div>}
  {loading&&<p>در حال بررسی دسترسی...</p>}
  {!loading&&role!=='admin'&&<p>دسترسی به مرکز کنترل مدیریتی فقط برای مدیر سازمان مجاز است.</p>}
  {role==='admin'&&<>
   <div className="statsGrid">
    {tiles.map(([key,label,url])=><Link key={key} href={url} className="statCard">
     <small>{label}</small><strong>{typeof summary?.[key]==='number'?summary[key]:'—'}</strong><span>نمایش گردش‌کار ←</span>
    </Link>)}
   </div>
   <section className="panel" style={{padding:18,marginTop:18}}>
    <div className="panelHeader"><h2>صف اقدامات مدیر</h2>
     <select aria-label="فیلتر صف" value={category} onChange={e=>void changeCategory(e.target.value)}>
      {categories.map(([id,label])=><option key={id} value={id}>{label}</option>)}
     </select>
    </div>
    <p>صف از محدوده‌ای از رکوردهای جدید هر دسته ساخته شده است و شمارش آن لزوماً کل سوابق سازمان نیست. هیچ اقدام پزشکی یا پیامی خودکار انجام نمی‌شود.</p>
    <div className="tableScroll"><table><thead><tr><th>اهمیت</th><th>نوع</th><th>پرونده</th><th>وضعیت</th><th>مسیر پیگیری</th></tr></thead>
     <tbody>{queue?.items.length?queue.items.map(x=><tr key={x.category+'-'+x.id}>
      <td>{x.priority==='urgent'?'فوری':x.priority==='high'?'بالا':'عادی'}</td>
      <td>{categories.find(c=>c[0]===x.category)?.[1]||x.category}</td>
      <td>{x.case_id?.slice(0,8)||'—'}</td><td>{x.status}</td>
      <td><Link href={x.destination}>بازکردن گردش‌کار مرتبط</Link></td>
     </tr>):<tr><td colSpan={5}>موردی در محدوده نمایش یافت نشد.</td></tr>}</tbody></table></div>
   </section>
   <section className="panel" style={{padding:18,marginTop:18}}>
    <h2>جستجوی مدیریتی بدون متن پزشکی</h2>
    <form onSubmit={search} className="formGrid">
     <label>عبارت حداقل سه کاراکتر
      <input value={term} onChange={e=>setTerm(e.target.value)} maxLength={80}
       minLength={3} required placeholder="شناسه، نام بیمار آزمایشی یا وضعیت پرونده"/>
     </label>
     <label>دامنه
      <select value={domain} onChange={e=>setDomain(e.target.value)}>
       <option value="all">همه</option><option value="patients">بیماران</option>
       <option value="cases">پرونده‌ها</option><option value="operations">خدمات</option>
      </select>
     </label>
     <div className="formActions"><button className="button" disabled={busy||term.trim().length<3}>جستجو</button></div>
    </form>
    <div className="tableScroll"><table><thead><tr><th>نوع</th><th>شناسه</th><th>برچسب اداری</th><th>پیگیری</th></tr></thead>
     <tbody>{results.map(x=><tr key={x.type+x.id}>
      <td>{x.type}</td><td>{x.id.slice(0,12)}</td><td>{x.label}</td>
      <td>{x.case_id?<button type="button" disabled={busy} onClick={()=>void showCase(x.case_id!)}>نمای پرونده</button>:
       <Link href={x.destination}>بازکردن</Link>}</td>
     </tr>)}</tbody></table></div>
    {overview&&<div style={{marginTop:12,padding:14,border:'1px solid #ccd8df',borderRadius:8}}>
     <h3>نمای خلاصه پرونده {selectedCase.slice(0,12)}</h3>
     <p>وضعیت: {overview.status} · مسئول: {overview.assigned_operator_id?.slice(0,8)||'تعیین‌نشده'}</p>
     <p>رضایت پذیرش: {overview.intake_consent?'موجود':'ناموجود'} · رضایت ارتباطات: {overview.communication_consent?'موجود':'ناموجود'}</p>
     <p>پیگیری‌های باز: {overview.open_followups} · خدمات معلق: {overview.pending_operations}</p>
     <p>تأیید بالینی: انجام نشده · اطلاعات پزشکی خام: ارائه نشده</p>
     <Link href="/journey">بازکردن مسیر بیمار</Link>
    </div>}
   </section>
   <section className="panel" style={{padding:18,marginTop:18}}>
    <h2>مدیریت امن دسترسی کارکنان</h2>
    <p>غیرفعال‌سازی مدیر فعلی یا حساب دارای کارهای باز/مالکیت فعال مجاز نیست. ابتدا از صفحات مربوط، وظایف را به فرد دیگری واگذار یا با مرجع معتبر ببندید.</p>
    <div style={{display:'flex',flexWrap:'wrap',gap:10}}>
     <select aria-label="کارمند مورد نظر" value={target} onChange={e=>setTarget(e.target.value)}>
      <option value="">انتخاب حساب فعال</option>
      {staff.filter(x=>x.active&&x.id!==selfId).map(x=><option key={x.id} value={x.id}>{x.email} ({x.role})</option>)}
     </select>
     <button type="button" disabled={!target||busy} onClick={()=>void deactivate()}>غیرفعال‌سازی با تأیید</button>
    </div>
   </section>
  </>}
 </Shell>;
}
