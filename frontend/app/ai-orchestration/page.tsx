'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Agent={agent_key:string;enabled:boolean;provider_mode:string;allowed_workflows:string[];daily_run_limit:number};
type Run={id:string;workflow:string;status:string;locale:string;display_text:string;mode:string;sent:boolean};
export default function AiOrchestrationPage(){
 const [agents,setAgents]=useState<Agent[]>([]);
 const [items,setItems]=useState<Run[]>([]);
 const [role,setRole]=useState('');
 const [key,setKey]=useState('administrative_receptionist');
 const [task,setTask]=useState('general_information');
 const [locale,setLocale]=useState('fa');
 const [mode,setMode]=useState('deterministic_demo');
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 const selected=agents.find(a=>a.agent_key===key);
 async function refresh(){
  const [catalog,runs,me]=await Promise.all([
   request<{agents:Agent[]}>('/ai-orchestration/catalog'),
   request<{items:Run[]}>('/ai-orchestration/runs'),
   request<{role:string}>('/auth/me')
  ]);
  setAgents(catalog.agents);setItems(runs.items);setRole(me.role);
 }
 useEffect(()=>{void refresh().catch(e=>setError((e as Error).message));},[]);
 async function action(path:string,body:object,method='POST'){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method,body:JSON.stringify(body)});
   await refresh();
   setNotice('عملیات داخلی ثبت شد. هیچ اقدام خارجی اجرا نشده است.');
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Shell title="مدیریت عامل‌های AI">
  <div className="infoBanner">
   محیط آزمایشی مدیریت عامل‌های اداری. استفاده از اطلاعات پزشکی، ارسال خودکار پیام، تصمیم درمانی و اقدام مالی یا رزرو غیرفعال است. خروجی مدل فقط پیش‌نویس نیازمند تأیید انسانی است.
  </div>
  {error&&<div className="errorBox">{error}</div>}
  {notice&&<div className="infoBanner">{notice}</div>}
  <section className="panel" style={{padding:20,marginTop:15}}>
   <h2>سیاست عامل‌ها</h2>
   <label>عامل<select value={key} onChange={e=>{setKey(e.target.value);setTask('');}}>
    {agents.map(a=><option key={a.agent_key} value={a.agent_key}>{a.agent_key} — {a.enabled?'فعال':'غیرفعال'}</option>)}
   </select></label>
   <label>حالت<select value={mode} onChange={e=>setMode(e.target.value)}>
    <option value="deterministic_demo">قالب ثابت غیرهوشمند</option>
    <option value="approved_provider">مدل با ارائه‌دهنده تأییدشده</option>
   </select></label>
   {role==='admin'&&<div style={{display:'flex',gap:12}}>
    <button className="button" disabled={busy} onClick={()=>void action('/ai-orchestration/agents/'+key,{enabled:true,provider_mode:mode,daily_run_limit:20},'PUT')}>فعال‌سازی آزمایشی</button>
    <button className="button secondary" disabled={busy} onClick={()=>void action('/ai-orchestration/agents/'+key,{enabled:false,provider_mode:mode,daily_run_limit:20},'PUT')}>غیرفعال‌سازی</button>
   </div>}
  </section>
  <section className="panel" style={{padding:20,marginTop:15}}>
   <h2>اجرای گردش‌کار غیرکلینیکی</h2>
   <label>کار<select value={task||selected?.allowed_workflows[0]||''} onChange={e=>setTask(e.target.value)}>
    {selected?.allowed_workflows.map(x=><option key={x} value={x}>{x}</option>)}
   </select></label>
   <label>زبان<select value={locale} onChange={e=>setLocale(e.target.value)}>
    {['fa','ar','en','ps','prs'].map(x=><option key={x} value={x}>{x}</option>)}
   </select></label>
   <button className="button" disabled={busy||!selected?.enabled} onClick={()=>void action('/ai-orchestration/runs',{
    request_key:'DEMO-'+crypto.randomUUID(),agent_key:key,
    workflow:task||selected?.allowed_workflows[0],locale
   })}>ایجاد پیش‌نویس برای بررسی انسانی</button>
  </section>
  <section className="panel" style={{padding:20,marginTop:15}}>
   <h2>صف پیش‌نویس‌ها</h2>
   {items.map(x=><article key={x.id} style={{padding:14,borderBottom:'1px solid #d4dfe3'}}>
    <strong>{x.workflow} · {x.locale} · {x.status}</strong>
    <p style={{whiteSpace:'pre-wrap'}}>{x.display_text}</p>
    <p>حالت اجرا: {x.mode} · پیام ارسال‌شده: خیر</p>
    {role==='admin'&&['pending_human_review','blocked_quality_gate'].includes(x.status)&&
     <div style={{display:'flex',gap:10}}>
      <button className="button" disabled={busy||x.status==='blocked_quality_gate'} onClick={()=>void action('/ai-orchestration/runs/'+x.id+'/review',{decision:'approve_internal',evidence_reference:'DEMO-REVIEW-12345'})}>تأیید داخلی</button>
      <button className="button secondary" disabled={busy} onClick={()=>void action('/ai-orchestration/runs/'+x.id+'/review',{decision:'reject',evidence_reference:'DEMO-REJECT-12345'})}>رد</button>
     </div>}
   </article>)}
  </section>
 </Shell>;
}
