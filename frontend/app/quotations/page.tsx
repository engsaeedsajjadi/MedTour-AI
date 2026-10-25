'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request,downloadPdf} from '@/lib/api';

type Quote={id:string;case_id:string;currency:string;amount_minor:number;status:string};
type Case={id:string;status:string};
type Price={id:string;label:string;currency:string;amount_minor:number;source:string;valid_until:string};
type Version={id:string;version:number;status:string;total_minor:number;currency:string;lines:{label:string;units:number;line_total_minor:number;source_reference:string}[]};
const ROOT='/quotation-versions';
export default function Quotations(){
 const [quotes,setQuotes]=useState<Quote[]>([]),[cases,setCases]=useState<Case[]>([]),[prices,setPrices]=useState<Price[]>([]);
 const [quoteId,setQuoteId]=useState(''),[caseId,setCaseId]=useState(''),[currency,setCurrency]=useState('USD');
 const [priceId,setPriceId]=useState(''),[units,setUnits]=useState(1),[versions,setVersions]=useState<Version[]>([]);
 const [role,setRole]=useState(''),[reference,setReference]=useState('');
 const [notice,setNotice]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function load(){
  const [q,c,p,me]=await Promise.all([
   request<Quote[]>('/quotes'),request<Case[]>('/cases?limit=200'),request<Price[]>('/prices'),
   request<{role:string}>('/auth/me')
  ]);
  setQuotes(q);setCases(c);setPrices(p);setRole(me.role);
  setQuoteId(v=>v||q[0]?.id||'');setCaseId(v=>v||c[0]?.id||'');
  setPriceId(v=>v||p[0]?.id||'');
 }
 async function versionsFor(id:string){
  if(!id){setVersions([]);return}
  const out=await request<{items:Version[]}>(ROOT+'/quotes/'+encodeURIComponent(id));
  setVersions(out.items);
 }
 useEffect(()=>{load().catch(e=>setError((e as Error).message));},[]);
 useEffect(()=>{versionsFor(quoteId).catch(e=>setError((e as Error).message));},[quoteId]);
 async function act(path:string,method:string,body:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method,body:JSON.stringify(body)});
   setNotice('تغییرات مالی داخلی ثبت شد؛ قیمت یا پرداخت واقعی ارائه‌دهنده تأیید نشده است.');
   await load();
   if(quoteId)await versionsFor(quoteId);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const selected=quotes.find(x=>x.id===quoteId);
 const options=prices.filter(p=>p.currency===(selected?.currency||currency));
 return <Shell title="پیش‌فاکتورهای نسخه‌دار">
  <div className="infoBanner">فقط داده‌های ساختگی. هر نسخه از قیمت‌های ثبت‌شده و دارای منبع با ارز واحد محاسبه می‌شود. تبدیل ارز و نرخ لحظه‌ای انجام نمی‌شود. تأیید مدیر فقط داخلی است و معادل تأیید بیمارستان یا پرداخت نیست.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20}}>
   <h2>ایجاد پیش‌فاکتور پایه بدون مبلغ دستی</h2>
   <label>پرونده <select value={caseId} onChange={e=>setCaseId(e.target.value)}>
    {cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.status}</option>)}
   </select></label>
   <label>ارز <select value={currency} onChange={e=>setCurrency(e.target.value)}>
    {['USD','EUR','IRR','AED'].map(c=><option key={c} value={c}>{c}</option>)}
   </select></label>
   <button disabled={busy||!caseId} onClick={()=>void act('/quotes','POST',{
    case_id:caseId,currency,amount_minor:0,details:'Versioned source-bound quote'
   })}>ساخت پیش‌فاکتور</button>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>نسخه‌ها و آیتم‌های قیمت</h2>
   <label>پیش‌فاکتور <select value={quoteId} onChange={e=>setQuoteId(e.target.value)}>
    {quotes.map(q=><option key={q.id} value={q.id}>{q.id.slice(0,8)} — {q.currency} — {q.status}</option>)}
   </select></label>
   <label>منبع قیمت <select value={priceId} onChange={e=>setPriceId(e.target.value)}>
    <option value="">انتخاب منبع</option>
    {options.map(p=><option key={p.id} value={p.id}>{p.label}: {p.amount_minor} {p.currency} (واحد جزء)</option>)}
   </select></label>
   <label>تعداد <input type="number" min={1} max={100000} value={units} onChange={e=>setUnits(Number(e.target.value))}/></label>
   <button disabled={busy||!quoteId||!priceId||!units} onClick={()=>void act(ROOT+'/quotes/'+encodeURIComponent(quoteId)+'/draft','POST',{
    lines:[{price_id:priceId,units}]
   })}>ایجاد نسخه جدید با محاسبه خودکار</button>
   <p>برای نسخه‌های چندردیفی، API می‌تواند آرایه‌ای از ردیف‌ها بگیرد. در این رابط، هر نسخه نمونه یک‌ردیفی است.</p>
   <label>مرجع بازبینی مدیر <input value={reference} minLength={6} maxLength={100}
    onChange={e=>setReference(e.target.value)}/></label>
   {versions.map(v=><div key={v.id} style={{padding:12,borderBottom:'1px solid #d5dce4'}}>
    <strong>نسخه {v.version} — {v.status} — {v.total_minor} {v.currency} (واحد جزء)</strong>
    {v.lines.map((l,i)=><p key={i}>{l.label}: {l.units} × {l.line_total_minor/l.units} = {l.line_total_minor}</p>)}
    {v.status==='draft'&&role==='admin'&&<button disabled={busy||reference.length<6}
     onClick={()=>void act(ROOT+'/versions/'+v.id+'/approve','POST',{reference})}>تأیید داخلی نسخه</button>}
    {v.status==='approved'&&<button disabled={busy} onClick={()=>void downloadPdf(ROOT+'/versions/'+v.id+'/pdf','quotation-'+v.id+'.pdf').catch(e=>setError((e as Error).message))}>دریافت PDF نسخه تأییدشده</button>}
   </div>)}
  </section>
 </Shell>;
}
