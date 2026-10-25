'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
type Agent={id:string;name:string;country:string;referral_code:string;active:boolean};
type Agreement={id:string;contract_key:string;jurisdiction:string;currency:string;scope:string;max_budget_minor:number;status:string;government_or_legal_approval_verified:boolean};
type Referral={id:string;request_key:string;channel:string;campaign_code:string;status:string;patient_id:string|null;created_at:string};
type Draft={id:string;draft_key:string;activity_reference:string;amount_minor:number;status:string;payout_authorized:boolean};
type Event={event:string;entity_kind:string;created_at:string};
const root='/agent-network';
const states:Record<string,string>={draft:'پیش‌نویس',administratively_reviewed:'بررسی اداری (نه تأیید حقوقی)',rejected:'ردشده',suspended:'تعلیق‌شده',submitted:'منتظر تطبیق با رضایت',attributed:'منتسب با رضایت',blocked:'مسدود پس از لغو رضایت',blocked_legal_review:'مسدود تا بررسی حقوقی'};
function status(x:string){return states[x]||x;}
export default function Agents(){
 const [agents,setAgents]=useState<Agent[]>([]),[selected,setSelected]=useState('');
 const [contracts,setContracts]=useState<Agreement[]>([]),[refs,setRefs]=useState<Referral[]>([]);
 const [drafts,setDrafts]=useState<Draft[]>([]),[history,setHistory]=useState<Event[]>([]);
 const [name,setName]=useState(''),[country,setCountry]=useState('AF');
 const [jurisdiction,setJurisdiction]=useState('AF'),[currency,setCurrency]=useState('USD'),[scope,setScope]=useState('nonclinical_marketing'),[budget,setBudget]=useState('100000');
 const [documentRef,setDocumentRef]=useState(''),[email,setEmail]=useState(''),[password,setPassword]=useState('');
 const [patientId,setPatientId]=useState(''),[commercialRef,setCommercialRef]=useState(''),[feeAmount,setFeeAmount]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const selectedAgent=agents.find(x=>x.id===selected);
 const latestContract=contracts.find(x=>x.status==='administratively_reviewed');
 async function reloadAgents(){
  const xs=await request<Agent[]>('/agents');setAgents(xs);setSelected(x=>x||xs[0]?.id||'');
 }
 async function reloadSelected(id:string){
  if(!id){setContracts([]);setRefs([]);setDrafts([]);setHistory([]);return;}
  const encoded=encodeURIComponent(id);
  const [c,r,d,h]=await Promise.all([
   request<{items:Agreement[]}>(root+'/agents/'+encoded+'/agreements'),
   request<{items:Referral[]}>(root+'/agents/'+encoded+'/referrals'),
   request<{items:Draft[]}>(root+'/agents/'+encoded+'/commercial-drafts'),
   request<{items:Event[]}>(root+'/agents/'+encoded+'/history')]);
  setContracts(c.items);setRefs(r.items);setDrafts(d.items);setHistory(h.items);
 }
 useEffect(()=>{(async()=>{
  const xs=await request<Agent[]>('/agents');setAgents(xs);
  const id=xs[0]?.id||'';setSelected(id);if(id)await reloadSelected(id);
 })().catch(e=>setError((e as Error).message));},[]);
 async function send(path:string,payload:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method:'POST',body:JSON.stringify(payload)});
   setNotice('عملیات اداری ثبت شد؛ تأیید قانونی، اعطای دسترسی بیمار و پرداخت به‌صورت خودکار انجام نمی‌شود.');
   await reloadAgents();if(selected)await reloadSelected(selected);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Shell title="مدیریت نمایندگان بین‌المللی">
  <div className="infoBanner">نسخه Alpha با داده‌های ساختگی. قراردادها صرفاً بررسی اداری می‌شوند و اعتبار قانونی ندارند. کارمزد مرتبط با بیمار یا پرداخت واقعی مجاز نیست. نمایندگان هیچ اطلاعات هویتی یا پزشکی بیمار را دریافت نمی‌کنند.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۱. تعریف نماینده</h2>
   <div style={{display:'grid',gap:10,maxWidth:630}}>
    <label>نام غیرحساس آزمایشی<input value={name} onChange={e=>setName(e.target.value)}/></label>
    <label>کشور<input value={country} onChange={e=>setCountry(e.target.value)}/></label>
    <button disabled={busy||name.length<2||country.length<2} onClick={()=>void send('/agents',{name,country})}>ثبت نماینده</button>
    <label>نماینده انتخاب‌شده<select value={selected} onChange={e=>{setSelected(e.target.value);void reloadSelected(e.target.value).catch(x=>setError((x as Error).message));}}>
     <option value="">انتخاب</option>{agents.map(a=><option key={a.id} value={a.id}>{a.name} · {a.country} · {a.active?'فعال':'غیرفعال'}</option>)}
    </select></label>
    {selectedAgent&&<p>کد ارجاع داخلی: <code>{selectedAgent.referral_code}</code> · وضعیت: {selectedAgent.active?'فعال':'غیرفعال'}</p>}
   </div>
  </section>
  {selectedAgent&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۲. قرارداد اداری خدمات غیر‌درمانی</h2>
   <div style={{display:'grid',gap:10,maxWidth:630}}>
    <label>کد کشور حوزه قرارداد (ISO 2)<input maxLength={2} value={jurisdiction} onChange={e=>setJurisdiction(e.target.value.toUpperCase())}/></label>
    <label>ارز (ISO 3)<input maxLength={3} value={currency} onChange={e=>setCurrency(e.target.value.toUpperCase())}/></label>
    <label>خدمات<select value={scope} onChange={e=>setScope(e.target.value)}>
     <option value="nonclinical_marketing">بازاریابی غیر درمانی</option><option value="nonclinical_logistics">هماهنگی لجستیکی غیر درمانی</option>
    </select></label>
    <label>سقف پیشنهادی بودجه، واحد کوچک ارز<input type="number" min={0} value={budget} onChange={e=>setBudget(e.target.value)}/></label>
    <button disabled={busy} onClick={()=>void send(root+'/agents/'+selected+'/agreements',{
     contract_key:'AGR-'+crypto.randomUUID(),jurisdiction,currency,scope,max_budget_minor:Number(budget)
    })}>ایجاد پیش‌نویس قرارداد</button>
    <label>مرجع اداری سند (نه اطلاعات شخصی)<input value={documentRef} maxLength={100} onChange={e=>setDocumentRef(e.target.value)}/></label>
   </div>
   {contracts.map(c=><div key={c.id} style={{borderTop:'1px solid #d4dde7',padding:'12px 0'}}>
    <strong>{status(c.status)} · {c.scope}</strong>
    <p>حوزه: {c.jurisdiction} · سقف: {c.max_budget_minor.toLocaleString()} {c.currency} (واحد کوچک)</p>
    <p>قانونی تأییدشده: خیر · مجوز پرداخت: خیر</p>
    {c.status==='draft'&&<div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
     <button disabled={busy||documentRef.length<6} onClick={()=>void send(root+'/agreements/'+c.id+'/review',{decision:'administratively_reviewed',document_reference:documentRef})}>بررسی اداری (نه تأیید حقوقی)</button>
     <button disabled={busy||documentRef.length<6} onClick={()=>void send(root+'/agreements/'+c.id+'/review',{decision:'rejected',document_reference:documentRef})}>رد پیش‌نویس</button>
    </div>}
    {c.status==='administratively_reviewed'&&<button disabled={busy||documentRef.length<6} onClick={()=>void send(root+'/agreements/'+c.id+'/review',{decision:'suspended',document_reference:documentRef})}>تعلیق قرارداد</button>}
   </div>)}
  </section>}
  {selectedAgent&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۳. حساب مستقل نماینده</h2>
   <p>فقط بعد از بررسی اداری قرارداد؛ رمز اولیه را از یک مسیر امن و جداگانه به نماینده تحویل دهید. قابلیت MFA هنوز آماده نیست و استفاده واقعی مجاز نیست.</p>
   <div style={{display:'grid',gap:10,maxWidth:620}}>
    <label>ایمیل<input type="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>
    <label>رمز آزمایشی (حداقل ۱۶ نویسه)<input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
    <button disabled={busy||!latestContract||password.length<16} onClick={()=>void send(root+'/agents/'+selected+'/account',{email,password})}>ساخت حساب با نقش agent</button>
    <button disabled={busy||!selectedAgent.active} onClick={()=>void send(root+'/agents/'+selected+'/disable',{})}>غیرفعال‌سازی کامل نماینده و نشست‌ها</button>
   </div>
  </section>}
  {selectedAgent&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۴. انتساب ارجاع با رضایت اختصاصی بیمار</h2>
   <p>نماینده فقط کد پیگیری غیرحساس ارسال می‌کند. مدیر فقط پس از ثبت رضایت `intake` و `agent_referral` می‌تواند ارجاع را به بیمار موجود متصل کند.</p>
   <label>شناسه بیمار آزمایشی<input value={patientId} onChange={e=>setPatientId(e.target.value)}/></label>
   {refs.map(r=><div key={r.id} style={{padding:'12px 0',borderTop:'1px solid #d4dde7'}}>
    <strong>{r.request_key} · {status(r.status)}</strong>
    <p>کانال: {r.channel} · کمپین: {r.campaign_code}</p>
    <p>انتساب داخلی (فقط مدیر): {r.patient_id||'هنوز منتسب نشده'}</p>
    {r.status==='submitted'&&<button disabled={busy||!patientId} onClick={()=>void send(root+'/referrals/'+r.id+'/attribute',{patient_id:patientId})}>انتساب با رضایت بیمار</button>}
   </div>)}
  </section>}
  {selectedAgent&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۵. پیش‌نویس هزینه خدمات غیر‌درمانی</h2>
   <p>همه مبالغ تا بررسی مستقل قوانین محلی، تضاد منافع، تحریم‌ها و سیاست‌های ارجاع بیمار «مسدود» هستند؛ هیچ پرداخت یا محاسبه کارمزد به‌ازای بیمار انجام نمی‌شود.</p>
   <div style={{display:'grid',gap:10,maxWidth:630}}>
    <label>مرجع فعالیت غیر بالینی<input value={commercialRef} onChange={e=>setCommercialRef(e.target.value)}/></label>
    <label>مبلغ پیشنهادی (واحد کوچک ارز قرارداد)<input type="number" min={1} value={feeAmount} onChange={e=>setFeeAmount(e.target.value)}/></label>
    <button disabled={busy||!latestContract||commercialRef.length<6||Number(feeAmount)<=0} onClick={()=>void send(root+'/agents/'+selected+'/commercial-drafts',{
     draft_key:'COST-'+crypto.randomUUID(),agreement_id:latestContract?.id||'',
     activity_reference:commercialRef,amount_minor:Number(feeAmount)})}>ثبت برآورد مسدود (بدون پرداخت)</button>
   </div>
   {drafts.map(x=><p key={x.id}>{x.activity_reference||x.draft_key} · {x.amount_minor.toLocaleString()} · {status(x.status)} · قابل پرداخت: خیر</p>)}
  </section>}
  {selectedAgent&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>۶. ردپای حسابرسی</h2>
   {history.slice(0,30).map((h,i)=><p key={i}>{new Date(h.created_at).toLocaleString('fa-IR')} · {h.event} · {h.entity_kind}</p>)}
  </section>}
 </Shell>;
}
