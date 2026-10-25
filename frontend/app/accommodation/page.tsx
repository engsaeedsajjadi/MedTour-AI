'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Hotel={id:string;name:string;city:string;status:string};
type Capacity={id:string;room_type:string;proposed_rooms:number;starts_on:string;ends_on:string;status:string;reference:string};
type CaseRow={id:string;patient_id:string;status:string};
type Stay={id:string;case_id:string;property_id:string;room_type:string;starts_on:string;ends_on:string;
 rooms_requested:number;guests:number;status:string;inventory_id:string|null;
 internal_reference:string|null;supplier_name:string|null;supplier_reference:string|null;
 provider_booking_independently_verified:boolean};
type Event={action:string;current:string;previous:string;reference:string;at:string};
const ROOT='/accommodation';
const labels:Record<string,string>={
 requested:'درخواست داخلی',internally_held:'تخصیص داخلی',
 external_request_reported:'تماس با هتل گزارش شد',
 external_confirmation_reported:'پاسخ مثبت هتل (ثبت دستی، اعتبارسنجی‌نشده)',
 external_decline_reported:'عدم‌تأیید گزارش‌شده',cancelled:'لغو داخلی',
 blocked:'مسدود پس از لغو رضایت',single:'یک‌تخته',double:'دوتخته',
 accessible:'دسترس‌پذیر',proposed:'ظرفیت پیشنهادی',revoked:'لغوشده'
};
const label=(x:string)=>labels[x]||x;
const roomTypes=['single','double','accessible'];
const today=()=>new Date().toISOString().slice(0,10);
const tomorrow=()=>new Date(Date.now()+86400000).toISOString().slice(0,10);
const afterWeek=()=>new Date(Date.now()+7*86400000).toISOString().slice(0,10);
export default function Accommodation(){
 const [role,setRole]=useState(''),[hotels,setHotels]=useState<Hotel[]>([]),[cases,setCases]=useState<CaseRow[]>([]);
 const [caseId,setCaseId]=useState(''),[propertyId,setPropertyId]=useState('');
 const [hotelName,setHotelName]=useState(''),[city,setCity]=useState('');
 const [roomType,setRoomType]=useState('double'),[start,setStart]=useState(tomorrow()),[end,setEnd]=useState(afterWeek());
 const [rooms,setRooms]=useState(1),[guests,setGuests]=useState(2),[inventoryCount,setInventoryCount]=useState(1);
 const [reference,setReference]=useState(''),[supplier,setSupplier]=useState('');
 const [capacity,setCapacity]=useState<Capacity[]>([]),[stays,setStays]=useState<Stay[]>([]);
 const [history,setHistory]=useState<Record<string,Event[]>>({});
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 async function loadProperties(){
  const p=await request<{items:Hotel[]}>(ROOT+'/properties');
  setHotels(p.items);setPropertyId(prev=>prev||p.items[0]?.id||'');
 }
 async function loadCapacity(pid:string){
  if(!pid){setCapacity([]);return;}
  const x=await request<{items:Capacity[]}>(ROOT+'/properties/'+encodeURIComponent(pid)+'/inventory');
  setCapacity(x.items);
 }
 async function loadStays(cid:string){
  if(!cid){setStays([]);return;}
  const x=await request<{items:Stay[]}>(ROOT+'/cases/'+encodeURIComponent(cid)+'/stays');
  setStays(x.items);
 }
 useEffect(()=>{(async()=>{
  const [me,cs,ps]=await Promise.all([
   request<{role:string}>('/auth/me'),request<CaseRow[]>('/cases?limit=200'),
   request<{items:Hotel[]}>(ROOT+'/properties')]);
  setRole(me.role);setCases(cs);setCaseId(cs[0]?.id||'');setHotels(ps.items);
  setPropertyId(ps.items[0]?.id||'');
  if(cs[0])await loadStays(cs[0].id);
  if(ps.items[0])await loadCapacity(ps.items[0].id);
 })().catch(e=>setError((e as Error).message));},[]);
 async function submit(path:string,body:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method:'POST',body:JSON.stringify(body)});
   setNotice('هماهنگی داخلی ثبت شد؛ این سامانه به موجودی یا رزرو قطعی هتل متصل نیست.');
   await Promise.all([loadProperties(),loadStays(caseId),loadCapacity(propertyId)]);
  }catch(e){setError((e as Error).message)}finally{setBusy(false);}
 }
 async function historyFor(id:string){
  try{
   const x=await request<{items:Event[]}>(ROOT+'/stays/'+id+'/history');
   setHistory(old=>({...old,[id]:x.items}));
  }catch(e){setError((e as Error).message);}
 }
 function transition(id:string,action:string){
  if(!/^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$/.test(reference)){
   setError('مرجع اداری غیرحساس و معتبر، حداقل ۶ کاراکتر لازم است.');return;
  }
  void submit(ROOT+'/stays/'+id+'/transition',{
   step_key:'STEP-'+crypto.randomUUID(),action,reference,
   supplier_name:action.startsWith('report_provider')?supplier:null
  });
 }
 return <Shell title="هماهنگی اقامت و هتل">
  <div className="infoBanner">
   فقط داده ساختگی در محیط توسعه. فهرست هتل‌ها و ظرفیت‌های آن‌ها صرفاً ثبت محلی هستند و با سامانه واقعی هتل همگام‌سازی نمی‌شوند. تخصیص داخلی یا ثبت پاسخ مثبت ارائه‌دهنده، به معنی رزرو تأییدشده نیست. این صفحه برای اطلاعات هویتی، گذرنامه و شرح پزشکی بیمار نیست.
  </div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  {role==='admin'&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۱. معرفی محل اقامت (ثبت داخلی)</h2>
   <div style={{display:'grid',gap:10,maxWidth:540}}>
    <label>نام هتل آزمایشی<input value={hotelName} onChange={e=>setHotelName(e.target.value)}/></label>
    <label>شهر<input value={city} onChange={e=>setCity(e.target.value)}/></label>
    <button disabled={busy||hotelName.length<3||city.length<2} onClick={()=>void submit(
     ROOT+'/properties',{name:hotelName,city})}>ثبت محل اقامت داخلی</button>
   </div>
  </section>}
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۲. ظرفیت پیشنهادی اتاق</h2>
   <div style={{display:'grid',gap:10,maxWidth:590}}>
    <label>محل اقامت<select value={propertyId} onChange={e=>{
     setPropertyId(e.target.value);
     void loadCapacity(e.target.value).catch(x=>setError((x as Error).message));
    }}><option value="">انتخاب</option>{hotels.map(h=><option key={h.id} value={h.id}>{h.name} — {h.city}</option>)}</select></label>
    <label>نوع اتاق<select value={roomType} onChange={e=>setRoomType(e.target.value)}>
     {roomTypes.map(x=><option key={x} value={x}>{label(x)}</option>)}</select></label>
    <label>ورود (شامل این شب)<input type="date" min={today()} value={start} onChange={e=>setStart(e.target.value)}/></label>
    <label>خروج (روز خروج شامل اقامت نیست)<input type="date" min={start} value={end} onChange={e=>setEnd(e.target.value)}/></label>
    {role==='admin'&&<>
     <label>تعداد اتاق پیشنهادی<input type="number" min={1} max={100} value={inventoryCount} onChange={e=>setInventoryCount(Number(e.target.value))}/></label>
     <label>مرجع اداری غیرحساس<input value={reference} onChange={e=>setReference(e.target.value)}/></label>
     <button disabled={busy||!propertyId||!start||!end||end<=start||reference.length<6}
      onClick={()=>void submit(ROOT+'/properties/'+propertyId+'/inventory',{
       room_type:roomType,starts_on:start,ends_on:end,
       proposed_rooms:inventoryCount,reference
      })}>ثبت ظرفیت پیشنهادی (نه موجودی زنده)</button>
    </>}
   </div>
   <div style={{marginTop:12}}>
    {capacity.map(c=><div key={c.id} style={{display:'flex',gap:10,flexWrap:'wrap',alignItems:'center',borderTop:'1px solid #d4dde7',padding:'10px 0'}}>
     <span>{label(c.room_type)} · {c.proposed_rooms} اتاق · {c.starts_on} تا {c.ends_on} · {label(c.status)}</span>
     {role==='admin'&&c.status==='proposed'&&<button disabled={busy} onClick={()=>void submit(ROOT+'/inventory/'+c.id+'/revoke',{})}>لغو ظرفیت آزاد</button>}
    </div>)}
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۳. درخواست اقامت برای پرونده</h2>
   <p>رضایت «پذیرش اولیه» و رضایت جداگانه «هماهنگی اقامت» باید برای بیمار فعال باشد. فعال‌سازی رضایت از مسیر امن و با اطلاع بیمار انجام می‌شود.</p>
   <div style={{display:'grid',gap:10,maxWidth:590}}>
    <label>پرونده<select value={caseId} onChange={e=>{
     setCaseId(e.target.value);setHistory({});
     void loadStays(e.target.value).catch(x=>setError((x as Error).message));
    }}><option value="">انتخاب پرونده</option>{cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} · {c.status}</option>)}</select></label>
    <label>تعداد اتاق برای پرونده<input type="number" min={1} max={5} value={rooms} onChange={e=>setRooms(Number(e.target.value))}/></label>
    <label>تعداد مهمان (بدون نام و اطلاعات هویتی)<input type="number" min={1} max={20} value={guests} onChange={e=>setGuests(Number(e.target.value))}/></label>
    <button disabled={busy||!caseId||!propertyId||!start||!end||end<=start}
     onClick={()=>void submit(ROOT+'/cases/'+encodeURIComponent(caseId)+'/stays',{
      request_key:'STAY-'+crypto.randomUUID(),property_id:propertyId,
      room_type:roomType,starts_on:start,ends_on:end,rooms_requested:rooms,guests
     })}>ثبت درخواست؛ بدون رزرو خارجی</button>
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۴. مراحل پیگیری داخلی</h2>
   <label>نام مرجع ارائه‌دهنده برای گزارش تماس (حداقل ۶ حرف لاتین)
    <input maxLength={100} value={supplier} onChange={e=>setSupplier(e.target.value)} placeholder="Synthetic Hotel Desk"/>
   </label>
   {stays.length===0?<p>برای این پرونده درخواستی موجود نیست یا رضایت فعال نیست.</p>:
    stays.map(s=><div key={s.id} style={{borderTop:'1px solid #d4dde7',padding:'14px 0',display:'grid',gap:10}}>
     <strong>{label(s.status)} · {label(s.room_type)} · {s.rooms_requested} اتاق / {s.guests} نفر</strong>
     <small>{s.starts_on} تا {s.ends_on} · هتل: {hotels.find(h=>h.id===s.property_id)?.name||s.property_id.slice(0,8)}</small>
     <small>مرجع داخلی: {s.internal_reference||'ندارد'} · گزارش ارائه‌دهنده: {s.supplier_reference||'ندارد'}</small>
     <small>رزرو مستقل هتل تأییدشده: خیر</small>
     {role==='admin'&&<div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
      {s.status==='requested'&&<button disabled={busy||reference.length<6} onClick={()=>transition(s.id,'hold_internally')}>تخصیص از ظرفیت پیشنهادی</button>}
      {s.status==='internally_held'&&<button disabled={busy||reference.length<6||supplier.length<6} onClick={()=>transition(s.id,'report_provider_request')}>ثبت گزارش تماس با هتل</button>}
      {s.status==='external_request_reported'&&<>
       <button disabled={busy||reference.length<6||supplier.length<6} onClick={()=>transition(s.id,'report_provider_confirmation')}>ثبت پاسخ مثبت (بدون تأیید مستقل)</button>
       <button disabled={busy||reference.length<6||supplier.length<6} onClick={()=>transition(s.id,'report_provider_decline')}>ثبت پاسخ منفی</button>
      </>}
      {['requested','internally_held'].includes(s.status)&&
       <button disabled={busy||reference.length<6} onClick={()=>transition(s.id,'cancel')}>لغو درخواست داخلی</button>}
     </div>}
     <button disabled={busy} onClick={()=>void historyFor(s.id)}>نمایش سوابق</button>
     {history[s.id]?.map((e,i)=><p key={i}>{new Date(e.at).toLocaleString('fa-IR')} · {e.action} · {label(e.previous)} → {label(e.current)} · {e.reference}</p>)}
    </div>)}
  </section>
 </Shell>;
}
