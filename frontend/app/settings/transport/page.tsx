'use client';
import {useEffect,useState} from 'react';
import SettingsPageFrame from '@/components/SettingsPageFrame';
import {request} from '@/lib/api';
import {cell} from '@/lib/i18n';
import {LANGUAGE_NAMES} from '@/lib/preferences';

type Resource={id:string;kind:'vehicle'|'interpreter';label:string;city:string;seats:number;language:string|null};
type Window={id:string;starts_at:string;ends_at:string;status:string;reference:string};
const ROOT='/travel-coordination';
const REF=/^[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}$/;
const local=(d:number,h:number)=>{const x=new Date(Date.now()+d*86400000);x.setHours(h,0,0,0);return new Date(x.getTime()-x.getTimezoneOffset()*60000).toISOString().slice(0,16);};

export default function TransportSettings(){
 const [items,setItems]=useState<Resource[]>([]),[selected,setSelected]=useState(''),[windows,setWindows]=useState<Window[]>([]);
 const [kind,setKind]=useState<'vehicle'|'interpreter'>('vehicle'),[label,setLabel]=useState(''),[city,setCity]=useState(''),[seats,setSeats]=useState(4),[lang,setLang]=useState('fa');
 const [start,setStart]=useState(local(1,8)),[end,setEnd]=useState(local(1,16)),[ref,setRef]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function loadItems(){const x=await request<{items:Resource[]}>(ROOT+'/resources');setItems(x.items);setSelected(v=>v||x.items[0]?.id||'');return x.items;}
 async function loadWindows(id:string){if(!id){setWindows([]);return;}setWindows((await request<{items:Window[]}>(ROOT+'/resources/'+encodeURIComponent(id)+'/windows')).items);}
 useEffect(()=>{loadItems().then(r=>loadWindows(r[0]?.id||'')).catch(e=>setError((e as Error).message));},[]);
 async function run(work:()=>Promise<unknown>,done:string){setBusy(true);setError('');setNotice('');
  try{await work();setNotice(done);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const add=(e:React.FormEvent)=>{e.preventDefault();void run(async()=>{
  const r=await request<Resource>(ROOT+'/resources',{method:'POST',body:JSON.stringify({kind,label,city,seats:kind==='vehicle'?seats:1,language:kind==='interpreter'?lang:null})});
  setLabel('');await loadItems();setSelected(r.id);await loadWindows(r.id);},'ثبت شد. حالا زمان‌هایی را که در دسترس است وارد کنید.');};
 const addWindow=(e:React.FormEvent)=>{e.preventDefault();
  if(!REF.test(ref)){setError('مرجع هماهنگی را با حروف لاتین و اعداد (حداقل ۶ نویسه) وارد کنید.');return;}
  void run(async()=>{await request(ROOT+'/resources/'+encodeURIComponent(selected)+'/windows',{method:'POST',
   body:JSON.stringify({starts_at:new Date(start).toISOString(),ends_at:new Date(end).toISOString(),reference:ref})});setRef('');await loadWindows(selected);},'زمان در دسترس ثبت شد.');};
 const revoke=(id:string)=>void run(async()=>{await request(ROOT+'/windows/'+id+'/revoke',{method:'POST',body:'{}'});await loadWindows(selected);},'لغو شد.');
 const current=items.find(x=>x.id===selected);

 return <SettingsPageFrame title="خودروها و مترجمان" error={error} notice={notice}
  intro="خودروهای ترانسفر و مترجمان همکار و زمان‌هایی که در دسترس هستند را اینجا ثبت کنید. در صفحه «ترانسفر و مترجم» برای هر بیمار از همین فهرست انتخاب می‌شود. نام راننده، شماره پلاک یا اطلاعات شخصی را وارد نکنید.">
  <section className="panel"><div className="panelHeader"><h2>افزودن خودرو یا مترجم</h2></div>
   <form className="formGrid" onSubmit={add}>
    <label>نوع<select value={kind} onChange={e=>setKind(e.target.value as 'vehicle'|'interpreter')}><option value="vehicle">خودرو</option><option value="interpreter">مترجم</option></select></label>
    <label>عنوان (مثلاً «ون ۷ نفره» یا «مترجم عربی ۱»)<input required minLength={3} maxLength={120} value={label} onChange={e=>setLabel(e.target.value)}/></label>
    <label>شهر<input required minLength={2} maxLength={80} value={city} onChange={e=>setCity(e.target.value)}/></label>
    {kind==='vehicle'?<label>تعداد صندلی مسافر<input type="number" min={1} max={8} value={seats} onChange={e=>setSeats(Number(e.target.value))}/></label>
     :<label>زبان مترجم<select value={lang} onChange={e=>setLang(e.target.value)}>{Object.entries(LANGUAGE_NAMES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>}
    <div className="formActions"><button className="button" disabled={busy}>افزودن</button></div>
   </form>
  </section>
  <section className="panel"><div className="panelHeader"><h2>زمان‌های در دسترس</h2>
   <label className="inlineLabel">مورد <select value={selected} onChange={e=>{setSelected(e.target.value);void loadWindows(e.target.value).catch(x=>setError((x as Error).message));}}>
    {items.length===0&&<option value="">ابتدا خودرو یا مترجم اضافه کنید</option>}
    {items.map(r=><option key={r.id} value={r.id}>{r.label} — {r.city} ({r.kind==='vehicle'?r.seats.toLocaleString('fa-IR')+' صندلی':LANGUAGE_NAMES[r.language||'']||r.language})</option>)}</select></label></div>
   <form className="formGrid" onSubmit={addWindow}>
    <label>از<input type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label>
    <label>تا (حداکثر ۸ ساعت)<input type="datetime-local" value={end} onChange={e=>setEnd(e.target.value)}/></label>
    <label>مرجع هماهنگی (لاتین)<input dir="ltr" value={ref} onChange={e=>setRef(e.target.value)} placeholder="SHIFT-1405-08-12"/></label>
    <div className="formActions"><button className="button" disabled={busy||!current||end<=start}>ثبت زمان</button></div>
   </form>
   <div className="tableScroll"><table><thead><tr><th>از</th><th>تا</th><th>مرجع</th><th>وضعیت</th><th></th></tr></thead><tbody>
    {windows.length===0?<tr><td className="empty" colSpan={5}>زمانی ثبت نشده است.</td></tr>:windows.map(w=><tr key={w.id}>
     <td>{cell('starts_at',w.starts_at)}</td><td>{cell('ends_at',w.ends_at)}</td><td dir="ltr">{w.reference}</td>
     <td><span className={'badge '+(w.status==='proposed'?'good':'muted')}>{w.status==='proposed'?'فعال':'لغوشده'}</span></td>
     <td>{w.status==='proposed'&&<button type="button" className="button secondary" disabled={busy} onClick={()=>revoke(w.id)}>لغو</button>}</td></tr>)}
   </tbody></table></div>
  </section>
 </SettingsPageFrame>;
}
