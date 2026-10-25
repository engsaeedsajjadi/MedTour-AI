'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Case={id:string;status:string};
type Resource={id:string;kind:'vehicle'|'interpreter';label:string;city:string;seats:number;language:string|null};
type Window={id:string;starts_at:string;ends_at:string;status:string};
type Assignment={id:string;kind:string;resource_id:string;status:string;starts_at:string;ends_at:string;
  passengers:number;language:string|null;origin_zone:string;destination_zone:string;external_dispatch_verified:boolean};
type History={action:string;before:string;after:string;reference:string;at:string};
const ROOT='/travel-coordination';
const kinds=['airport_pickup','airport_dropoff','city_transfer','interpreter_session'];
const names:Record<string,string>={vehicle:'خودرو/راننده (داخلی)',interpreter:'مترجم همراه',
 airport_pickup:'استقبال فرودگاهی',airport_dropoff:'بدرقه فرودگاهی',
 city_transfer:'ترانسفر شهری',interpreter_session:'جلسه مترجم',
 requested:'درخواست داخلی',internally_allocated:'تخصیص داخلی',
 provider_contact_reported:'تماس گزارش‌شده',provider_ack_reported:'پاسخ مثبت گزارش‌شده',
 provider_decline_reported:'پاسخ منفی گزارش‌شده',cancelled:'لغو داخلی',blocked:'مسدود به‌علت لغو رضایت',
 airport:'فرودگاه',hotel:'هتل',hospital:'بیمارستان',city_center:'مرکز شهر',not_applicable:'بدون مسیر'};
const label=(s:string)=>names[s]||s;
const zones=['airport','hotel','hospital','city_center','not_applicable'];
const later=(d:number)=>{const x=new Date(Date.now()+d*86400000);return new Date(x.getTime()-x.getTimezoneOffset()*60000).toISOString().slice(0,16);};
export default function TravelCoordination(){
 const [role,setRole]=useState(''),[cases,setCases]=useState<Case[]>([]),[caseId,setCaseId]=useState('');
 const [resources,setResources]=useState<Resource[]>([]),[resourceId,setResourceId]=useState('');
 const [kind,setKind]=useState('airport_pickup'),[labelResource,setLabelResource]=useState(''),[city,setCity]=useState('');
 const [seats,setSeats]=useState(4),[language,setLanguage]=useState('fa');
 const [start,setStart]=useState(later(7)),[end,setEnd]=useState(later(7).slice(0,11)+'16:00');
 const [passengers,setPassengers]=useState(2),[origin,setOrigin]=useState('airport'),[dest,setDest]=useState('hotel');
 const [reference,setReference]=useState(''),[supplier,setSupplier]=useState('');
 const [rows,setRows]=useState<Assignment[]>([]),[windows,setWindows]=useState<Window[]>([]);
 const [history,setHistory]=useState<Record<string,History[]>>({});
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 async function loadResources(){
  const x=await request<{items:Resource[]}>(ROOT+'/resources');
  setResources(x.items);setResourceId(v=>v||x.items[0]?.id||'');
 }
 async function loadCase(id:string){
  if(!id){setRows([]);return;}
  const x=await request<{items:Assignment[]}>(ROOT+'/cases/'+encodeURIComponent(id)+'/requests');
  setRows(x.items);
 }
 async function loadWindows(id:string){
  if(!id){setWindows([]);return;}
  const x=await request<{items:Window[]}>(ROOT+'/resources/'+encodeURIComponent(id)+'/windows');
  setWindows(x.items);
 }
 useEffect(()=>{(async()=>{
  const [me,cs,rs]=await Promise.all([
   request<{role:string}>('/auth/me'),request<Case[]>('/cases?limit=200'),
   request<{items:Resource[]}>(ROOT+'/resources')
  ]);
  setRole(me.role);setCases(cs);setResources(rs.items);
  setCaseId(cs[0]?.id||'');setResourceId(rs.items[0]?.id||'');
  if(cs[0])await loadCase(cs[0].id);
  if(rs.items[0])await loadWindows(rs.items[0].id);
 })().catch(e=>setError((e as Error).message));},[]);
 async function send(path:string,body:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method:'POST',body:JSON.stringify(body)});
   setNotice('ثبت داخلی موفق بود؛ تأیید یا اعزام واقعی ارائه‌دهنده دریافت نشده است.');
   await Promise.all([loadResources(),loadCase(caseId),loadWindows(resourceId)]);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 const type=kind==='interpreter_session'?'interpreter':'vehicle';
 const resource=resources.find(x=>x.id===resourceId);
 const originValue=type==='interpreter'?'not_applicable':origin;
 const destValue=type==='interpreter'?'not_applicable':dest;
 function submitRequest(){
  if(!resource||resource.kind!==type){setError('منبع را متناسب با نوع خدمت انتخاب کنید.');return;}
  void send(ROOT+'/cases/'+encodeURIComponent(caseId)+'/requests',{
   request_key:'MOVE-'+crypto.randomUUID(),resource_id:resourceId,kind,
   starts_at:new Date(start).toISOString(),ends_at:new Date(end).toISOString(),
   passengers:type==='interpreter'?1:passengers,language:type==='interpreter'?resource.language:null,
   origin_zone:originValue,destination_zone:destValue
  });
 }
 function change(id:string,action:string){
  if(reference.length<6){setError('مرجع غیرحساس حداقل ۶ نویسه لازم است.');return;}
  void send(ROOT+'/requests/'+id+'/transition',{
   step_key:'STEP-'+crypto.randomUUID(),action,reference,
   supplier_name:action.startsWith('report_provider')?supplier:null
  });
 }
 async function showHistory(id:string){
  try{const v=await request<{items:History[]}>(ROOT+'/requests/'+id+'/history');
   setHistory(x=>({...x,[id]:v.items}));}
  catch(e){setError((e as Error).message);}
 }
 return <Shell title="ترانسفر، حمل‌ونقل و مترجم">
  <div className="infoBanner">فقط داده ساختگی. منابع و ظرفیت‌ها پیشنهاد داخلی هستند؛ مجوز راننده/مترجم، اعزام، رزرو و حضور واقعی مستقلاً تأیید نشده‌اند. هیچ شماره پرواز، نام همراه، آدرس، گذرنامه یا اطلاعات درمانی در این صفحه وارد نکنید. رضایت جداگانه «transport_coordination» یا «interpreter_coordination» و پذیرش اولیه باید فعال باشد.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  {role==='admin'&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۱. منبع همکاری (ثبت داخلی و بدون تأیید مجوز)</h2>
   <div style={{display:'grid',gap:10,maxWidth:610}}>
    <label>نوع<select value={type} onChange={e=>setKind(e.target.value==='interpreter'?'interpreter_session':'airport_pickup')}>
     <option value="vehicle">خودرو</option><option value="interpreter">مترجم</option>
    </select></label>
    <label>نام نمایشی غیرحساس منبع<input value={labelResource} onChange={e=>setLabelResource(e.target.value)}/></label>
    <label>شهر<input value={city} onChange={e=>setCity(e.target.value)}/></label>
    {type==='vehicle'?<label>ظرفیت صندلی پیشنهادی<input type="number" min={1} max={8} value={seats} onChange={e=>setSeats(Number(e.target.value))}/></label>:
     <label>زبان مترجم<select value={language} onChange={e=>setLanguage(e.target.value)}>
      {['fa','en','ar','ps','prs'].map(x=><option key={x} value={x}>{x}</option>)}
     </select></label>}
    <button disabled={busy||labelResource.length<3||city.length<2} onClick={()=>void send(ROOT+'/resources',{
     kind:type,label:labelResource,city,seats:type==='vehicle'?seats:1,language:type==='interpreter'?language:null
    })}>ثبت منبع اداری</button>
   </div>
  </section>}
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۲. بازه زمانی و ظرفیت پیشنهادی</h2>
   <div style={{display:'grid',gap:10,maxWidth:610}}>
    <label>منبع<select value={resourceId} onChange={e=>{setResourceId(e.target.value);void loadWindows(e.target.value).catch(x=>setError((x as Error).message));}}>
     <option value="">انتخاب منبع</option>{resources.map(r=><option key={r.id} value={r.id}>{r.label} ({label(r.kind)})</option>)}
    </select></label>
    <label>شروع<input type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label>
    <label>پایان<input type="datetime-local" value={end} onChange={e=>setEnd(e.target.value)}/></label>
    <label>مرجع اداری غیرحساس<input value={reference} onChange={e=>setReference(e.target.value)}/></label>
    {role==='admin'&&<button disabled={busy||!resourceId||!start||!end||end<=start||reference.length<6}
      onClick={()=>void send(ROOT+'/resources/'+resourceId+'/windows',{
       starts_at:new Date(start).toISOString(),ends_at:new Date(end).toISOString(),reference
      })}>ثبت بازه پیشنهادی</button>}
    {windows.map(w=><div key={w.id} style={{padding:8,borderTop:'1px solid #d4dde7'}}>
     <span>{new Date(w.starts_at).toLocaleString('fa-IR')} تا {new Date(w.ends_at).toLocaleString('fa-IR')} · {w.status}</span>
     {role==='admin'&&w.status==='proposed'&&<button disabled={busy} onClick={()=>void send(ROOT+'/windows/'+w.id+'/revoke',{})}>لغو بازه آزاد</button>}
    </div>)}
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۳. درخواست برای پرونده بیمار</h2>
   <div style={{display:'grid',gap:10,maxWidth:610}}>
    <label>پرونده<select value={caseId} onChange={e=>{setCaseId(e.target.value);void loadCase(e.target.value).catch(x=>setError((x as Error).message));}}>
     <option value="">انتخاب پرونده</option>{cases.map(x=><option key={x.id} value={x.id}>{x.id.slice(0,8)} · {x.status}</option>)}
    </select></label>
    <label>نوع خدمت<select value={kind} onChange={e=>setKind(e.target.value)}>
     {kinds.map(x=><option key={x} value={x}>{label(x)}</option>)}
    </select></label>
    <p>منبع انتخاب‌شده: {resource?.label||'انتخاب نشده'} · لازم: {label(type)}</p>
    {type==='vehicle'&&<>
     <label>تعداد مسافر<input type="number" value={passengers} min={1} max={8} onChange={e=>setPassengers(Number(e.target.value))}/></label>
     <label>مبدأ کلی<select value={origin} onChange={e=>setOrigin(e.target.value)}>
      {zones.filter(x=>x!=='not_applicable').map(x=><option value={x} key={x}>{label(x)}</option>)}
     </select></label>
     <label>مقصد کلی<select value={dest} onChange={e=>setDest(e.target.value)}>
      {zones.filter(x=>x!=='not_applicable').map(x=><option value={x} key={x}>{label(x)}</option>)}
     </select></label>
    </>}
    <button disabled={busy||!caseId||!resource||resource.kind!==type||!start||!end||end<=start}
       onClick={submitRequest}>ایجاد درخواست داخلی</button>
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۴. تخصیص و پیگیری انسانی</h2>
   <label>عنوان میز ارائه‌دهنده (فقط برای گزارش تماس)<input value={supplier} onChange={e=>setSupplier(e.target.value)} placeholder="Synthetic Vendor Desk"/></label>
   {rows.map(x=><div key={x.id} style={{padding:'14px 0',borderTop:'1px solid #d4dde7'}}>
    <strong>{label(x.kind)} · {label(x.status)} · {new Date(x.starts_at).toLocaleString('fa-IR')}</strong>
    <p>منبع: {resources.find(r=>r.id===x.resource_id)?.label||x.resource_id.slice(0,8)} · اعزام خارجی تأییدشده: خیر</p>
    {role==='admin'&&<div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
     {x.status==='requested'&&<button disabled={busy||reference.length<6} onClick={()=>change(x.id,'allocate_internally')}>تخصیص داخلی</button>}
     {x.status==='internally_allocated'&&<button disabled={busy||reference.length<6||supplier.length<6} onClick={()=>change(x.id,'report_provider_contact')}>ثبت گزارش تماس</button>}
     {x.status==='provider_contact_reported'&&<>
      <button disabled={busy||reference.length<6||supplier.length<6} onClick={()=>change(x.id,'report_provider_ack')}>ثبت پاسخ مثبت (غیررسمی)</button>
      <button disabled={busy||reference.length<6||supplier.length<6} onClick={()=>change(x.id,'report_provider_decline')}>ثبت پاسخ منفی</button>
     </>}
     {['requested','internally_allocated'].includes(x.status)&&<button disabled={busy||reference.length<6} onClick={()=>change(x.id,'cancel')}>لغو داخلی</button>}
    </div>}
    <button disabled={busy} onClick={()=>void showHistory(x.id)}>تاریخچه</button>
    {history[x.id]?.map((h,i)=><p key={i}>{new Date(h.at).toLocaleString('fa-IR')} · {h.action} · {label(h.before)} ← {label(h.after)} · {h.reference}</p>)}
   </div>)}
  </section>
 </Shell>;
}
