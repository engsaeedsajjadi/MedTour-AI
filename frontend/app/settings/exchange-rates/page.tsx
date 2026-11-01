'use client';
import {useEffect,useState} from 'react';
import SettingsPageFrame from '@/components/SettingsPageFrame';
import {request} from '@/lib/api';
import {cell} from '@/lib/i18n';
import {CURRENCIES} from '@/lib/preferences';

type Rate={id:string;source_currency:string;target_currency:string;numerator:number;denominator:number;source_reference:string;expires_at:string;status?:string};
const ROOT='/quotation-versions';
const inDays=(d:number)=>{const x=new Date(Date.now()+d*86400000);return new Date(x.getTime()-x.getTimezoneOffset()*60000).toISOString().slice(0,16);};

export default function ExchangeRates(){
 const [rates,setRates]=useState<Rate[]>([]);
 const [from,setFrom]=useState('EUR'),[to,setTo]=useState('USD'),[num,setNum]=useState('108'),[den,setDen]=useState('100'),[ref,setRef]=useState(''),[expires,setExpires]=useState(inDays(7));
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const load=async()=>setRates((await request<{items:Rate[]}>(ROOT+'/fx-rates')).items);
 useEffect(()=>{load().catch(e=>setError((e as Error).message));},[]);
 async function run(work:()=>Promise<unknown>,done:string){setBusy(true);setError('');setNotice('');
  try{await work();setNotice(done);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const add=(e:React.FormEvent)=>{e.preventDefault();void run(async()=>{
  await request(ROOT+'/fx-rates',{method:'POST',body:JSON.stringify({source_currency:from,target_currency:to,numerator:Number(num),denominator:Number(den),source_reference:ref,expires_at:new Date(expires).toISOString()})});
  setRef('');await load();},'نرخ ارز ثبت شد و در پیش‌فاکتورها قابل انتخاب است.');};
 const revoke=(id:string)=>void run(async()=>{await request(ROOT+'/fx-rates/'+id+'/revoke',{method:'POST',body:'{}'});await load();},'نرخ لغو شد.');
 const example=Number(num)>0&&Number(den)>0?(Number(num)/Number(den)).toLocaleString('fa-IR',{maximumFractionDigits:6}):'—';

 return <SettingsPageFrame title="نرخ ارز" error={error} notice={notice}
  intro="نرخ تبدیل ارز را از منبع رسمی (مثلاً نرخ اعلامی بانک) با شماره یا تاریخ مرجع ثبت کنید. هر نرخ حداکثر ۳۰ روز اعتبار دارد و پس از آن در پیش‌فاکتور جدید قابل استفاده نیست.">
  <section className="panel"><div className="panelHeader"><h2>ثبت نرخ جدید</h2></div>
   <form className="formGrid" onSubmit={add}>
    <label>ارز مبدأ<select value={from} onChange={e=>setFrom(e.target.value)}>{CURRENCIES.map(c=><option key={c}>{c}</option>)}</select></label>
    <label>ارز مقصد<select value={to} onChange={e=>setTo(e.target.value)}>{CURRENCIES.map(c=><option key={c}>{c}</option>)}</select></label>
    <label>صورت نسبت (بر حسب کوچک‌ترین واحد ارز)<input type="number" min={1} step={1} required value={num} onChange={e=>setNum(e.target.value)}/></label>
    <label>مخرج نسبت<input type="number" min={1} step={1} required value={den} onChange={e=>setDen(e.target.value)}/></label>
    <p className="subtle settingsWide">هر ۱ واحد کوچک {from} = {example} واحد کوچک {to}</p>
    <label>مرجع نرخ (لاتین، مثلاً تاریخ و منبع)<input dir="ltr" required minLength={6} value={ref} onChange={e=>setRef(e.target.value)} placeholder="CBI-RATE-2026-11-01"/></label>
    <label>اعتبار تا (حداکثر ۳۰ روز)<input type="datetime-local" required value={expires} onChange={e=>setExpires(e.target.value)}/></label>
    <div className="formActions"><button className="button" disabled={busy||from===to}>ثبت نرخ</button></div>
   </form>
  </section>
  <section className="panel"><div className="panelHeader"><h2>نرخ‌های ثبت‌شده</h2></div>
   <div className="tableScroll"><table><thead><tr><th>از</th><th>به</th><th>نسبت</th><th>مرجع</th><th>اعتبار تا</th><th></th></tr></thead><tbody>
    {rates.length===0?<tr><td className="empty" colSpan={6}>نرخی ثبت نشده است.</td></tr>:rates.map(r=><tr key={r.id}>
     <td>{r.source_currency}</td><td>{r.target_currency}</td><td dir="ltr">{r.numerator}/{r.denominator}</td><td dir="ltr">{r.source_reference}</td><td>{cell('expires_at',r.expires_at)}</td>
     <td>{(!r.status||r.status==='active')&&<button type="button" className="button secondary" disabled={busy} onClick={()=>revoke(r.id)}>لغو</button>}</td></tr>)}
   </tbody></table></div>
  </section>
 </SettingsPageFrame>;
}
