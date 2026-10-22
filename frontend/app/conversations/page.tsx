'use client';

import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Thread={
 conversation_id:string;patient_id:string;channel:string;language:string;
 status:'open'|'assigned'|'waiting'|'resolved';priority:string;
 assigned_user_id:string|null;human_handoff:boolean;
};
type Message={id:string;sender:string;body:string;language:string;created_at:string};
type Event={action:string;reference:string|null;from_status:string;to_status:string;created_at:string};
type Staff={id:string;email:string;role:string;active:boolean};
type Readiness={internal_webchat_available:boolean;live_whatsapp_send_verified:boolean;
 chatwoot_sync_live_verified:boolean;real_patient_data_allowed:boolean};
const LANG=[['fa','فارسی'],['ar','العربية'],['en','English'],['ps','پښتو'],['prs','دری']];
const STATUS:Record<string,string>={open:'باز و بدون مسئول',assigned:'در اختیار اپراتور',
 waiting:'منتظر پاسخ انسانی',resolved:'پایان یافته'};
export default function Conversations(){
 const [threads,setThreads]=useState<Thread[]>([]);
 const [messages,setMessages]=useState<Message[]>([]);
 const [events,setEvents]=useState<Event[]>([]);
 const [staff,setStaff]=useState<Staff[]>([]);
 const [myId,setMyId]=useState('');
 const [role,setRole]=useState('');
 const [readiness,setReadiness]=useState<Readiness|null>(null);
 const [active,setActive]=useState('');
 const [statusFilter,setStatusFilter]=useState('');
 const [assigneeFilter,setAssigneeFilter]=useState('all');
 const [target,setTarget]=useState('');
 const [text,setText]=useState('');
 const [language,setLanguage]=useState('fa');
 const [reference,setReference]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const current=threads.find(t=>t.conversation_id===active);
 const isAssigned=!!current?.assigned_user_id&&current.assigned_user_id===myId;
 const canReply=!!current&&current.channel==='webchat'&&current.status!=='resolved'&&
  (role==='admin'||isAssigned);

 async function reload(filter=statusFilter,assigned=assigneeFilter){
  const query=new URLSearchParams({limit:'100',assigned});
  if(filter)query.set('status',filter);
  const res=await request<{items:Thread[]}>('/inbox/threads?'+query.toString());
  setThreads(res.items);
  if(active&&!res.items.some(t=>t.conversation_id===active)){
   setActive('');setMessages([]);setEvents([]);
  }
 }
 async function loadThread(id:string){
  setActive(id);setMessages([]);setEvents([]);setError('');
  try{
   const [msgs,history]=await Promise.all([
    request<Message[]>('/inbox/threads/'+encodeURIComponent(id)+'/messages?limit=100'),
    request<{items:Event[]}>('/inbox/threads/'+encodeURIComponent(id)+'/events'),
   ]);
   setMessages(msgs);setEvents(history.items);
  }catch(e){setError((e as Error).message)}
 }
 useEffect(()=>{
  (async()=>{
   const me=await request<{id:string;role:string}>('/auth/me');
   setMyId(me.id);setRole(me.role);
   const [res,ready]=await Promise.all([
    request<{items:Thread[]}>('/inbox/threads'),
    request<Readiness>('/inbox/readiness'),
   ]);
   setThreads(res.items);setReadiness(ready);
   if(me.role==='admin'){
    setStaff((await request<Staff[]>('/staff')).filter(
     x=>x.active&&(x.role==='admin'||x.role==='operator')));
   }
  })().catch(e=>setError((e as Error).message));
 },[]);
 async function changeFilter(status:string,assigned:string){
  setStatusFilter(status);setAssigneeFilter(assigned);setError('');
  try{await reload(status,assigned)}catch(e){setError((e as Error).message)}
 }
 async function action(route:string,payload?:unknown){
  if(!active)return;
  setBusy(true);setError('');setNotice('');
  try{
   await request('/inbox/threads/'+encodeURIComponent(active)+'/'+route,{
    method:'POST',...(payload?{body:JSON.stringify(payload)}:{})
   });
   setNotice('اقدام انسانی ثبت شد؛ هیچ پیام خارجی به صورت خودکار ارسال نشده است.');
   await reload();
   await loadThread(active);
   setReference('');
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function send(e:React.FormEvent){
  e.preventDefault();if(!active||!text.trim())return;
  setBusy(true);setError('');setNotice('');
  try{
   const result=await request<{stored_in_portal:boolean;external_provider_sent:boolean}>(
    '/inbox/threads/'+encodeURIComponent(active)+'/reply',{
      method:'POST',body:JSON.stringify({body:text,language}),
    });
   setText('');
   setNotice(result.stored_in_portal?'پاسخ فقط در وب‌چت امن ثبت شد؛ ارسال بیرونی انجام نشد.':'نتیجه نامشخص است.');
   await reload();await loadThread(active);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <Shell title="صندوق مکالمات انسانی">
  <div className="infoBanner">
   این صندوق، گفت‌وگوهای داخلی و بازبینی انسانی را برای داده‌های ساختگی مدیریت می‌کند. اتصال زنده Chatwoot/WhatsApp تأیید نشده است؛ اطلاعات پزشکی واقعی وارد نکنید. علامت فوریت فقط هشدار احتیاطی واژه‌ای است، نه تریاژ پزشکی.
  </div>
  {error&&<p role="alert" className="errorBox">{error}</p>}
  {notice&&<p role="status" className="infoBanner">{notice}</p>}
  <section className="panel" style={{padding:16,marginBottom:16}}>
   <strong>آمادگی اتصال‌ها:</strong>
   <span> وب‌چت داخلی: {readiness?.internal_webchat_available?'آماده تست':'نامشخص'}</span>
   <span> | WhatsApp زنده: {readiness?.live_whatsapp_send_verified?'تأیید شده':'تأیید نشده'}</span>
   <span> | Chatwoot زنده: {readiness?.chatwoot_sync_live_verified?'تأیید شده':'تأیید نشده'}</span>
   <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:12}}>
    <label>وضعیت
     <select value={statusFilter} onChange={e=>void changeFilter(e.target.value,assigneeFilter)}>
      <option value="">همه</option>{Object.entries(STATUS).map(([k,v])=><option key={k} value={k}>{v}</option>)}
     </select>
    </label>
    <label>مسئول
     <select value={assigneeFilter} onChange={e=>void changeFilter(statusFilter,e.target.value)}>
      <option value="all">مجاز به مشاهده</option><option value="mine">مکالمات من</option><option value="unassigned">بدون مسئول</option>
     </select>
    </label>
    <button type="button" disabled={busy} onClick={()=>void reload()}>بازخوانی صف</button>
   </div>
  </section>
  <div className="inbox">
   <section className="panel threadList">
    <div className="panelHeader"><h2>صف مکالمات</h2><small>{threads.length} مورد در محدوده</small></div>
    {threads.length===0?<p className="empty">مکالمه دارای رضایت فعال در این محدوده دیده نشد.</p>:threads.map(t=>
     <button type="button" key={t.conversation_id} className={active===t.conversation_id?'thread selected':'thread'}
      onClick={()=>void loadThread(t.conversation_id)}>
      <b>بیمار {t.patient_id.slice(0,8)} · {t.channel}</b>
      <small>{STATUS[t.status]||t.status} · {t.priority==='urgent'?'هشدار فوری':'عادی'}</small>
      <small>مسئول: {t.assigned_user_id?.slice(0,8)||'بدون مسئول'}</small>
     </button>)}
   </section>
   <section className="panel conversationPanel">
    <div className="panelHeader"><h2>گفت‌وگو و اقدامات</h2></div>
    {!current?<div className="empty">یک مکالمه انتخاب کنید.</div>:<>
     <div style={{padding:12,display:'flex',flexWrap:'wrap',gap:8}}>
      <span>وضعیت: <strong>{STATUS[current.status]}</strong></span>
      <span>اولویت: <strong>{current.priority==='urgent'?'فوری':'عادی'}</strong></span>
      <button type="button" disabled={busy||current.status==='resolved'||(!!current.assigned_user_id&&!isAssigned)}
       onClick={()=>void action('claim')}>دریافت مکالمه</button>
      {(isAssigned||role==='admin')&&current.status!=='resolved'&&current.assigned_user_id&&
       <button type="button" disabled={busy} onClick={()=>void action('release')}>آزادسازی</button>}
      {role==='admin'&&current.status!=='resolved'&&<>
       <select aria-label="کاربر گیرنده" value={target} onChange={e=>setTarget(e.target.value)}>
        <option value="">انتخاب اپراتور</option>{staff.map(u=><option key={u.id} value={u.id}>{u.email}</option>)}
       </select>
       <button type="button" disabled={busy||!target} onClick={()=>void action('assign',{assigned_user_id:target})}>واگذاری</button>
      </>}
     </div>
     <div className="messageStream">
      {messages.length===0?<p className="empty">پیامی ثبت نشده است.</p>:messages.map(m=>
       <div className="bubble" key={m.id}><small>{m.sender} · {m.language}</small>
        <p lang={m.language} dir={m.language==='en'?'ltr':'rtl'}>{m.body}</p>
       </div>)}
     </div>
     {canReply&&<form className="messageComposer" onSubmit={send}>
      <label>زبان
       <select value={language} onChange={e=>setLanguage(e.target.value)}>
        {LANG.map(([code,label])=><option key={code} value={code}>{label}</option>)}
       </select>
      </label>
      <input lang={language} dir={language==='en'?'ltr':'rtl'} required maxLength={4000}
       placeholder="پاسخ انسانی بازبینی‌شده، فقط در وب‌چت" value={text}
       onChange={e=>setText(e.target.value)}/>
      <button className="button" disabled={busy||!text.trim()}>ثبت پاسخ</button>
     </form>}
     <div style={{padding:12,borderTop:'1px solid #cbd5df'}}>
      <label>مرجع اداری غیرحساس (۶ تا ۱۰۰ کاراکتر)
       <input maxLength={100} minLength={6} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}"
        value={reference} onChange={e=>setReference(e.target.value)}
        placeholder="REF-CASE-00001"/>
      </label>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:10}}>
       {current.status!=='resolved'?<>
        <button type="button" disabled={busy||reference.length<6}
         onClick={()=>void action('wait',{reference})}>در انتظار بیمار</button>
        <button type="button" disabled={busy||reference.length<6}
         onClick={()=>void action('resolve',{reference})}>بستن انسانی</button>
       </>:<button type="button" disabled={busy||reference.length<6}
        onClick={()=>void action('reopen',{reference})}>بازکردن مجدد</button>}
      </div>
      <h3>تاریخچه اقدامات (بدون متن پزشکی)</h3>
      {events.length===0?<p>تاریخچه‌ای ثبت نشده است.</p>:events.map((ev,i)=>
       <p key={i}><small>{ev.action} · {ev.from_status} ← {ev.to_status}
        {ev.reference?' · '+ev.reference:''}</small></p>)}
     </div>
    </>}
   </section>
  </div>
 </Shell>;
}
