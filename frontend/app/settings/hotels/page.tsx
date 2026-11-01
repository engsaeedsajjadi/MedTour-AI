'use client';
import {useEffect,useState} from 'react';
import SettingsPageFrame from '@/components/SettingsPageFrame';
import {request} from '@/lib/api';
import {fmtDate} from '@/lib/i18n';

type Hotel={id:string;name:string;city:string;status:string};
type Capacity={id:string;room_type:string;proposed_rooms:number;starts_on:string;ends_on:string;status:string;reference:string};
const ROOT='/accommodation';
const ROOM:Record<string,string>={single:'یک‌تخته',double:'دوتخته',accessible:'مناسب معلولان'};
const STATUS:Record<string,string>={proposed:'فعال',revoked:'لغوشده'};
const REF=/^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$/;
const day=(n:number)=>new Date(Date.now()+n*86400000).toISOString().slice(0,10);

export default function HotelSettings(){
 const [hotels,setHotels]=useState<Hotel[]>([]),[selected,setSelected]=useState(''),[capacity,setCapacity]=useState<Capacity[]>([]);
 const [name,setName]=useState(''),[city,setCity]=useState('');
 const [room,setRoom]=useState('double'),[from,setFrom]=useState(day(1)),[to,setTo]=useState(day(90)),[rooms,setRooms]=useState(5),[ref,setRef]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function loadHotels(){const x=await request<{items:Hotel[]}>(ROOT+'/properties');setHotels(x.items);setSelected(v=>v||x.items[0]?.id||'');return x.items;}
 async function loadCapacity(id:string){if(!id){setCapacity([]);return;}setCapacity((await request<{items:Capacity[]}>(ROOT+'/properties/'+encodeURIComponent(id)+'/inventory')).items);}
 useEffect(()=>{loadHotels().then(h=>loadCapacity(h[0]?.id||'')).catch(e=>setError((e as Error).message));},[]);
 async function run(work:()=>Promise<unknown>,done:string){setBusy(true);setError('');setNotice('');
  try{await work();setNotice(done);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const addHotel=(e:React.FormEvent)=>{e.preventDefault();void run(async()=>{
  const h=await request<Hotel>(ROOT+'/properties',{method:'POST',body:JSON.stringify({name,city})});
  setName('');setCity('');await loadHotels();setSelected(h.id);await loadCapacity(h.id);},'هتل اضافه شد. حالا ظرفیت اتاق‌های قراردادی آن را ثبت کنید.');};
 const addCapacity=(e:React.FormEvent)=>{e.preventDefault();
  if(!REF.test(ref)){setError('شماره قرارداد یا نامه هتل را با حروف لاتین و اعداد (حداقل ۶ نویسه) وارد کنید.');return;}
  void run(async()=>{await request(ROOT+'/properties/'+encodeURIComponent(selected)+'/inventory',{method:'POST',
   body:JSON.stringify({room_type:room,starts_on:from,ends_on:to,proposed_rooms:rooms,reference:ref})});setRef('');await loadCapacity(selected);},'ظرفیت ثبت شد.');};
 const revoke=(id:string)=>void run(async()=>{await request(ROOT+'/inventory/'+id+'/revoke',{method:'POST',body:'{}'});await loadCapacity(selected);},'ظرفیت لغو شد.');

 return <SettingsPageFrame title="هتل‌ها و ظرفیت اتاق" error={error} notice={notice}
  intro="هتل‌های طرف قرارداد و تعداد اتاقی را که هر هتل برای بیماران شما در اختیار گذاشته یک بار اینجا ثبت کنید. درخواست اقامت هر بیمار در صفحه «اقامت و هتل» از همین ظرفیت برداشته می‌شود.">
  <section className="panel"><div className="panelHeader"><h2>افزودن هتل</h2></div>
   <form className="formGrid" onSubmit={addHotel}>
    <label>نام هتل<input required minLength={3} maxLength={150} value={name} onChange={e=>setName(e.target.value)}/></label>
    <label>شهر<input required minLength={2} maxLength={80} value={city} onChange={e=>setCity(e.target.value)}/></label>
    <div className="formActions"><button className="button" disabled={busy}>افزودن هتل</button></div>
   </form>
  </section>
  <section className="panel"><div className="panelHeader"><h2>ظرفیت اتاق</h2>
   <label className="inlineLabel">هتل <select value={selected} onChange={e=>{setSelected(e.target.value);void loadCapacity(e.target.value).catch(x=>setError((x as Error).message));}}>
    {hotels.length===0&&<option value="">ابتدا هتل اضافه کنید</option>}{hotels.map(h=><option key={h.id} value={h.id}>{h.name} — {h.city}</option>)}</select></label></div>
   <form className="formGrid" onSubmit={addCapacity}>
    <label>نوع اتاق<select value={room} onChange={e=>setRoom(e.target.value)}>{Object.entries(ROOM).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
    <label>تعداد اتاق<input type="number" min={1} max={100} value={rooms} onChange={e=>setRooms(Number(e.target.value))}/></label>
    <label>از تاریخ<input type="date" min={day(0)} value={from} onChange={e=>setFrom(e.target.value)}/></label>
    <label>تا تاریخ (حداکثر ۹۰ روز بعد)<input type="date" min={from} value={to} onChange={e=>setTo(e.target.value)}/></label>
    <label>شماره قرارداد یا نامه هتل (لاتین)<input dir="ltr" value={ref} onChange={e=>setRef(e.target.value)} placeholder="HOTEL-CONTRACT-1405-01"/></label>
    <div className="formActions"><button className="button" disabled={busy||!selected||to<=from}>ثبت ظرفیت</button></div>
   </form>
   <div className="tableScroll"><table><thead><tr><th>نوع اتاق</th><th>تعداد</th><th>از</th><th>تا</th><th>مرجع</th><th>وضعیت</th><th></th></tr></thead><tbody>
    {capacity.length===0?<tr><td className="empty" colSpan={7}>ظرفیتی ثبت نشده است.</td></tr>:capacity.map(c=><tr key={c.id}>
     <td>{ROOM[c.room_type]||c.room_type}</td><td>{c.proposed_rooms.toLocaleString('fa-IR')}</td><td>{fmtDate(c.starts_on)}</td><td>{fmtDate(c.ends_on)}</td><td dir="ltr">{c.reference}</td>
     <td><span className={'badge '+(c.status==='proposed'?'good':'muted')}>{STATUS[c.status]||c.status}</span></td>
     <td>{c.status==='proposed'&&<button type="button" className="button secondary" disabled={busy} onClick={()=>revoke(c.id)}>لغو</button>}</td></tr>)}
   </tbody></table></div>
  </section>
 </SettingsPageFrame>;
}
