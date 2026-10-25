'use client';

import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request,downloadPdf} from '@/lib/api';

type Quote={id:string;case_id:string;currency:string;amount_minor:number;status:string};
type CaseRow={id:string;status:string};
type Price={id:string;label:string;currency:string;amount_minor:number;source:string;valid_until:string};
type FxRate={id:string;source_currency:string;target_currency:string;numerator:number;denominator:number;source_reference:string;expires_at:string};
type QuoteLine={price_id:string;units:number;fx_rate_id:string|null};
type SnapshotLine={label:string;units:number;source_currency?:string;source_total_minor?:number;line_total_minor:number;source_reference:string;fx_source_reference?:string|null};
type Version={id:string;version:number;status:string;total_minor:number;currency:string;fx_conversion_used:boolean;lines:SnapshotLine[]};
const ROOT='/quotation-versions';
const currencies=['USD','EUR','IRR','AED'];
const freshLine=():QuoteLine=>({price_id:'',units:1,fx_rate_id:null});

export default function Quotations(){
 const [quotes,setQuotes]=useState<Quote[]>([]);
 const [cases,setCases]=useState<CaseRow[]>([]);
 const [prices,setPrices]=useState<Price[]>([]);
 const [rates,setRates]=useState<FxRate[]>([]);
 const [quoteId,setQuoteId]=useState('');
 const [caseId,setCaseId]=useState('');
 const [currency,setCurrency]=useState('USD');
 const [lines,setLines]=useState<QuoteLine[]>([freshLine()]);
 const [versions,setVersions]=useState<Version[]>([]);
 const [role,setRole]=useState('');
 const [reference,setReference]=useState('');
 const [rateFrom,setRateFrom]=useState('EUR'),[rateTo,setRateTo]=useState('USD');
 const [num,setNum]=useState('1'),[den,setDen]=useState('1');
 const [rateRef,setRateRef]=useState(''),[expires,setExpires]=useState('');
 const [notice,setNotice]=useState(''),[error,setError]=useState('');
 const [busy,setBusy]=useState(false);

 async function refresh(){
  const [q,c,p,me,fx]=await Promise.all([
   request<Quote[]>('/quotes'),
   request<CaseRow[]>('/cases?limit=200'),
   request<Price[]>('/prices'),
   request<{role:string}>('/auth/me'),
   request<{items:FxRate[]}>(ROOT+'/fx-rates'),
  ]);
  setQuotes(q);setCases(c);setPrices(p);setRole(me.role);setRates(fx.items);
  setQuoteId(prev=>prev||q[0]?.id||'');
  setCaseId(prev=>prev||c[0]?.id||'');
 }
 async function readVersions(id:string){
  if(!id){setVersions([]);return}
  const v=await request<{items:Version[]}>(ROOT+'/quotes/'+encodeURIComponent(id));
  setVersions(v.items);
 }
 useEffect(()=>{refresh().catch(e=>setError((e as Error).message));},[]);
 useEffect(()=>{readVersions(quoteId).catch(e=>setError((e as Error).message));},[quoteId]);
 const selected=quotes.find(q=>q.id===quoteId);
 const quoteCurrency=selected?.currency||currency;
 const activePrices=prices.filter(x=>new Date(x.valid_until).getTime()>Date.now());
 function changeLine(index:number,values:Partial<QuoteLine>){
  setLines(prev=>prev.map((l,i)=>i===index?{...l,...values}:l));
 }
 async function action(path:string,method:'POST',body:object){
  setBusy(true);setNotice('');setError('');
  try{
   const result=await request<{id?:string}>(path,{method,body:JSON.stringify(body)});
   setNotice('ثبت در سیستم داخلی انجام شد؛ این نتیجه تأیید مالی یا رزرو واقعی ارائه‌دهنده نیست.');
   await refresh();
   if(result.id&&path==='/quotes'){
    setQuoteId(result.id);await readVersions(result.id);
   }else if(quoteId)await readVersions(quoteId);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function createVersion(){
  if(!quoteId||lines.some(l=>!l.price_id||!Number.isInteger(l.units)||l.units<=0)){
   setError('ردیف‌ها و تعداد معتبر را تکمیل کنید.');return;
  }
  await action(ROOT+'/quotes/'+encodeURIComponent(quoteId)+'/draft','POST',{
   lines:lines.map(x=>({...x,fx_rate_id:x.fx_rate_id||null}))
  });
 }
 async function createRate(e:React.FormEvent){
  e.preventDefault();
  if(!expires||!num||!den)return;
  await action(ROOT+'/fx-rates','POST',{
   source_currency:rateFrom,target_currency:rateTo,
   numerator:Number(num),denominator:Number(den),
   source_reference:rateRef,expires_at:new Date(expires).toISOString()
  });
 }
 async function exportVersion(id:string){
  setError('');
  try{await downloadPdf(ROOT+'/versions/'+encodeURIComponent(id)+'/pdf','medtour-quotation-'+id+'.pdf')}
  catch(e){setError((e as Error).message)}
 }
 return <Shell title="پیش‌فاکتورها و نسخه‌های مالی">
  <div className="infoBanner">
   محیط توسعه، فقط داده ساختگی. قیمت‌ها و نرخ ارز باید از منابع واقعی به‌صورت دستی بررسی و مستند شوند؛ سامانه دریافت نرخ زنده، محاسبه قانونی مالیات، تأیید صورتحساب بیمارستان یا پرداخت واقعی ندارد. نسبت FX بر حسب کوچک‌ترین واحد پول مبدا به مقصد است، نه نرخ هر واحد اصلی.
  </div>
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {notice&&<div role="status" className="infoBanner">{notice}</div>}
  <section className="panel" style={{padding:20}}>
   <h2>۱. پیش‌فاکتور پایه</h2>
   <div style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'end'}}>
    <label>پرونده
     <select value={caseId} onChange={e=>setCaseId(e.target.value)}>
      {cases.map(x=><option key={x.id} value={x.id}>{x.id.slice(0,8)} · {x.status}</option>)}
     </select>
    </label>
    <label>ارز خروجی
     <select value={currency} onChange={e=>setCurrency(e.target.value)}>
      {currencies.map(x=><option key={x} value={x}>{x}</option>)}
     </select>
    </label>
    <button disabled={busy||!caseId} onClick={()=>void action('/quotes','POST',{
     case_id:caseId,currency,amount_minor:0,details:'Managed source-bound quote'
    })}>ایجاد پیش‌فاکتور بدون مبلغ دستی</button>
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۲. ردیف‌های هزینه و نسخه‌بندی</h2>
   <label>پیش‌فاکتور
    <select value={quoteId} onChange={e=>{setQuoteId(e.target.value);setLines([freshLine()])}}>
     <option value="">انتخاب</option>
     {quotes.map(x=><option key={x.id} value={x.id}>{x.id.slice(0,8)} · {x.currency} · {x.status}</option>)}
    </select>
   </label>
   <p>ارز نهایی: <strong>{quoteCurrency}</strong> · تعداد ردیف‌ها: {lines.length} از ۵۰</p>
   {lines.map((line,i)=>{
    const source=prices.find(p=>p.id===line.price_id);
    const fxOptions=rates.filter(r=>r.source_currency===source?.currency&&r.target_currency===quoteCurrency);
    return <div key={i} style={{padding:12,borderBottom:'1px solid #d3dce5',display:'grid',gap:8}}>
     <strong>ردیف {i+1}</strong>
     <label>خدمت و منبع مستند
      <select value={line.price_id} onChange={e=>changeLine(i,{price_id:e.target.value,fx_rate_id:null})}>
       <option value="">انتخاب منبع قیمت</option>
       {activePrices.map(p=><option key={p.id} value={p.id}>{p.label} · {p.amount_minor} {p.currency} (جزء) · {p.source}</option>)}
      </select>
     </label>
     <label>تعداد
      <input type="number" min={1} max={100000} value={line.units}
       onChange={e=>changeLine(i,{units:Number(e.target.value)})}/>
     </label>
     {source&&source.currency!==quoteCurrency&&<label>نرخ تبدیل تأییدشده دستی ({source.currency} به {quoteCurrency})
      <select value={line.fx_rate_id||''} onChange={e=>changeLine(i,{fx_rate_id:e.target.value||null})}>
       <option value="">انتخاب مدرک نرخ ارز</option>
       {fxOptions.map(r=><option key={r.id} value={r.id}>
        {r.numerator}/{r.denominator} · {r.source_reference} · تا {new Date(r.expires_at).toLocaleString('fa-IR')}
       </option>)}
      </select>
     </label>}
     {lines.length>1&&<button type="button" disabled={busy} onClick={()=>setLines(old=>old.filter((_,j)=>i!==j))}>حذف ردیف</button>}
    </div>
   })}
   <div style={{display:'flex',gap:9,flexWrap:'wrap',marginTop:12}}>
    <button type="button" disabled={busy||lines.length>=50} onClick={()=>setLines(prev=>[...prev,freshLine()])}>افزودن ردیف</button>
    <button type="button" disabled={busy||!quoteId||selected?.status!=='draft'}
     onClick={()=>void createVersion()}>محاسبه و ذخیره نسخه جدید</button>
   </div>
  </section>
  {role==='admin'&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۳. ثبت نرخ ارز مستند به‌دست مدیر</h2>
   <p>مقدار نمونه یا تخمینی ثبت نکنید. نسبت عدد صحیح «جزء پول مبدأ → جزء پول مقصد» همراه مرجع قابل پیگیری و انقضای حداکثر ۳۰ روز است؛ این سیستم صحت مرجع را به‌صورت مستقل اثبات نمی‌کند.</p>
   <form onSubmit={e=>void createRate(e)} style={{display:'grid',gap:9,maxWidth:590}}>
    <label>ارز مبدأ <select value={rateFrom} onChange={e=>setRateFrom(e.target.value)}>
     {currencies.map(x=><option key={x} value={x}>{x}</option>)}
    </select></label>
    <label>ارز مقصد <select value={rateTo} onChange={e=>setRateTo(e.target.value)}>
     {currencies.map(x=><option key={x} value={x}>{x}</option>)}
    </select></label>
    <label>صورت نسبت <input required type="number" min="1" max="1000000000000" step="1" value={num} onChange={e=>setNum(e.target.value)}/></label>
    <label>مخرج نسبت <input required type="number" min="1" max="1000000000000" step="1" value={den} onChange={e=>setDen(e.target.value)}/></label>
    <label>مرجع مکتوب غیرحساس <input required minLength={6} maxLength={180} pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,179}" value={rateRef} onChange={e=>setRateRef(e.target.value)}/></label>
    <label>انقضا (حداکثر ۳۰ روز) <input required type="datetime-local" value={expires} onChange={e=>setExpires(e.target.value)}/></label>
    <button disabled={busy||rateFrom===rateTo}>ثبت نرخ دستی قابل ممیزی</button>
   </form>
  </section>}
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۴. نسخه‌های ثبت‌شده و خروجی PDF</h2>
   <label>مرجع تأیید اداری <input value={reference} minLength={6} maxLength={100}
    pattern="[A-Za-z0-9][A-Za-z0-9._:/-]{5,99}"
    onChange={e=>setReference(e.target.value)}/></label>
   {versions.length===0?<p>نسخه‌ای برای این پیش‌فاکتور وجود ندارد.</p>:versions.map(v=>
    <div key={v.id} style={{padding:12,borderBottom:'1px solid #d4dde7'}}>
     <strong>نسخه {v.version} · {v.status} · {v.total_minor} {v.currency} (جزء ارز)</strong>
     {v.lines.map((l,i)=><p key={i}>{i+1}. {l.label}: {l.units} واحد · جمع {l.line_total_minor} {v.currency}
      {l.fx_source_reference?' · FX دستی: '+l.fx_source_reference:''}</p>)}
     {v.status==='draft'&&role==='admin'&&<button disabled={busy||reference.length<6}
      onClick={()=>void action(ROOT+'/versions/'+v.id+'/approve','POST',{reference})}>
      تأیید داخلی با بررسی منابع
     </button>}
     {v.status==='approved'&&<button disabled={busy} onClick={()=>void exportVersion(v.id)}>
      دریافت PDF چندصفحه‌ای نسخه تأییدشده
     </button>}
    </div>)}
  </section>
 </Shell>;
}
