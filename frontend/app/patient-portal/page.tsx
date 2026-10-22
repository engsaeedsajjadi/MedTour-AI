'use client';
import {useEffect,useState} from 'react';
import {API_BASE} from '@/lib/api';
type Journey={case_id:string,status:string,specialty:string,services:{service:string,status:string}[],confirmed_appointments:{at:string,reference:string}[],approved_quotes:{amount_minor:number,currency:string,id:string}[]};
type ChatMessage={sender:string,body:string,language:string};

const LANGUAGE_LABELS:Record<string,string>={fa:'فارسی',ar:'العربية',en:'English',ps:'پښتو',prs:'دری'};
const CHAT_UI:Record<string,{chat:string,placeholder:string,send:string,handoff:string,intake:string,answer:string,notice:string,language:string}>={
 fa:{chat:'گفتگوی امن هماهنگی',placeholder:'پیام برای هماهنگ‌کننده',send:'ارسال',handoff:'گفتگو به هماهنگ‌کننده انسانی ارجاع شده است.',intake:'فرم پذیرش',answer:'ثبت پاسخ',notice:'این سامانه خدمات اورژانس یا تشخیص ارائه نمی‌کند.',language:'زبان گفتگو'},
 ar:{chat:'محادثة التنسيق الآمنة',placeholder:'رسالة إلى المنسق',send:'إرسال',handoff:'تم تحويل المحادثة إلى منسق بشري.',intake:'استمارة الاستقبال',answer:'حفظ الإجابة',notice:'هذه الخدمة ليست للطوارئ أو التشخيص.',language:'لغة المحادثة'},
 en:{chat:'Secure coordination chat',placeholder:'Message your coordinator',send:'Send',handoff:'Conversation transferred to a human coordinator.',intake:'Intake form',answer:'Save answer',notice:'This service cannot provide emergency care or diagnosis.',language:'Conversation language'},
 ps:{chat:'خوندي اداري خبرې',placeholder:'همغږي کوونکي ته پیغام',send:'لېږل',handoff:'ستاسو خبرې انساني همغږي کوونکي ته وسپارل شوې.',intake:'د منلو فورمه',answer:'ځواب ثبت کړئ',notice:'دا خدمت بیړنۍ پاملرنه یا تشخیص نه وړاندې کوي.',language:'د خبرو ژبه'},
 prs:{chat:'گفتگوی مصون هماهنگی',placeholder:'پیام به هماهنگ‌کننده',send:'ارسال',handoff:'گفتگو به هماهنگ‌کننده انسانی راجع شد.',intake:'فورم پذیرش',answer:'ثبت جواب',notice:'این خدمت برای حالت عاجل یا تشخیص طبی نیست.',language:'زبان گفتگو'}
};

export default function PatientPortal(){
 const [token,setToken]=useState(''),[patient,setPatient]=useState<{name:string,language:string}|null>(null),[journey,setJourney]=useState<Journey[]>([]);
 const [intake,setIntake]=useState<{id:string;case_id:string;status:string;next_prompt:string|null;language:string;stage:number}|null>(null);
 const [intakeAnswer,setIntakeAnswer]=useState('');
 const [documentFile,setDocumentFile]=useState<File|null>(null);
 const [documentStatus,setDocumentStatus]=useState('');
 const [chatLocale,setChatLocale]=useState('en');
 const copy=CHAT_UI[chatLocale]||CHAT_UI.en;
 const [messages,setMessages]=useState<ChatMessage[]>([]),[input,setInput]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
   const hash=window.location.hash.slice(1);const code=hash.startsWith('access=')?decodeURIComponent(hash.slice(7)):'';
   if(code){sessionStorage.setItem('medtour_patient_access',code);window.history.replaceState({},'',window.location.pathname);}
   setToken(code||sessionStorage.getItem('medtour_patient_access')||'');
 },[]);
 async function call<T>(path:string,init:RequestInit={}):Promise<T>{const r=await fetch(`${API_BASE}/api/v1/portal${path}`,{...init,headers:{'Content-Type':'application/json','X-Patient-Access':token,...init.headers},cache:'no-store'});const data=await r.json();if(!r.ok)throw new Error(String(data.detail||'Request failed'));return data as T;}
 useEffect(()=>{if(!token)return;Promise.all([call<{name:string,language:string}>('/me'),call<Journey[]>('/journey'),call<ChatMessage[]>('/chat')]).then(([p,j,m])=>{setPatient(p);setChatLocale(CHAT_UI[p.language]?p.language:'en');setJourney(j);setMessages(m)}).catch(e=>setError(e.message));},[token]);
 async function send(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const result=await call<{warning:string|null,human_handoff:boolean,handoff_notice?:string|null}>('/chat',{method:'POST',body:JSON.stringify({message:input,language:chatLocale})});setMessages(await call<ChatMessage[]>('/chat'));setInput('');if(result.warning)setError(result.warning);else if(result.human_handoff)setError(result.handoff_notice||copy.handoff)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function startIntake(caseId:string){setBusy(true);setError('');try{setIntake(await call<NonNullable<typeof intake>>('/intake/sessions',{method:'POST',body:JSON.stringify({case_id:caseId,language:chatLocale})}));}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function answerIntake(e:React.FormEvent){e.preventDefault();if(!intake)return;setBusy(true);setError('');try{const out=await call<typeof intake&{warning?:string}>(`/intake/sessions/${intake.id}/answer`,{method:'POST',body:JSON.stringify({answer:intakeAnswer})});setIntake(out);setIntakeAnswer('');if(out.warning)setError(out.warning);}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function uploadDocument(caseId:string){if(!documentFile)return;setBusy(true);setDocumentStatus('');setError('');try{const body=new FormData();body.append('file',documentFile);const r=await fetch(`${API_BASE}/api/v1/secure-documents/portal/cases/${caseId}`,{method:'POST',headers:{'X-Patient-Access':token},body,cache:'no-store'});const result=await r.json();if(!r.ok)throw new Error(String(result.detail||'Upload unavailable'));setDocumentStatus(`Uploaded to authorized storage. File reference: ${result.id}`);setDocumentFile(null);}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const logout=()=>{sessionStorage.removeItem('medtour_patient_access');setToken('');setPatient(null);setJourney([]);setMessages([])};
 return <main style={{maxWidth:900,margin:'32px auto',padding:24,fontFamily:'system-ui',color:'#142b3c'}}>
 <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12}}><h1>✚ MedTour AI | Patient Portal</h1><button onClick={logout}>Clear access</button></header>
 <p>Secure coordination portal · بوابة المريض · پورتال بیمار</p><p>Information shown here is for administrative coordination; emergency care and clinical decisions require qualified local services.</p>
 {error&&<div role="alert" style={{background:'#ffefdd',padding:16,borderRadius:10}}>{error}</div>}
 {!patient?<p>Open the short-lived private link provided by your coordinator. Do not share it.</p>:<><h2 dir="auto">{patient.name}</h2>
 {journey.map(c=><section key={c.case_id} style={{border:'1px solid #cedae0',padding:20,margin:'16px 0',borderRadius:12}}><h3>Medical case · {c.specialty||'Medical service'} — {c.status}</h3>
 <small>Reference: {c.case_id}</small><p><button disabled={busy} onClick={()=>startIntake(c.case_id)}>Start / resume structured intake</button></p><div style={{border:'1px solid #d2e5e0',padding:12,borderRadius:8,margin:'10px 0'}}><h4>Secure medical document upload</h4><p>PDF/JPG/PNG up to 8 MiB; only after your explicit document consent and secure storage setup.</p><input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setDocumentFile(e.target.files?.[0]||null)}/><button disabled={busy||!documentFile} onClick={()=>uploadDocument(c.case_id)}>Upload securely</button>{documentStatus&&<p>{documentStatus}</p>}</div><h4>Travel and care coordination</h4>{c.services.length===0?<p>No active services.</p>:c.services.map((s,i)=><p key={i}>{s.service} — {s.status}</p>)}
 <h4>Confirmed appointments</h4>{c.confirmed_appointments.map((a,i)=><p key={i}>{a.at} — {a.reference}</p>)}
 <h4>Approved estimates</h4>{c.approved_quotes.map(q=><p key={q.id}>{q.amount_minor} minor units / {q.currency}</p>)}</section>)}
 {intake&&<section style={{border:'2px solid #168f83',padding:20,margin:'16px 0',borderRadius:12}}><h3>{copy.intake} · {intake.status}</h3><small>Step {intake.stage+1} / 5</small>{intake.next_prompt?<form onSubmit={answerIntake}><p dir="auto" style={{fontSize:18}}>{intake.next_prompt}</p><textarea dir="auto" required maxLength={3000} value={intakeAnswer} onChange={e=>setIntakeAnswer(e.target.value)} style={{width:'100%'}}/><p><button disabled={busy}>{copy.answer}</button></p></form>:<p>Submitted for qualified human review. Do not use this service in an emergency.</p>}</section>}
 <section style={{border:'1px solid #cedae0',padding:20,borderRadius:12}}><h3>{copy.chat}</h3><label>{copy.language} <select aria-label={copy.language} value={chatLocale} onChange={e=>setChatLocale(e.target.value)}>{Object.keys(LANGUAGE_LABELS).map(code=><option key={code} value={code}>{LANGUAGE_LABELS[code]}</option>)}</select></label><p>{copy.notice}</p><div style={{maxHeight:390,overflowY:'auto',background:'#f6f9fb',padding:16,borderRadius:8}}>{messages.map((m,i)=><div key={i} style={{padding:10,margin:'8px 0',background:'#fff',borderRadius:8}}><small>{m.sender}</small><div dir="auto">{m.body}</div></div>)}</div><form onSubmit={send} style={{display:'flex',gap:8,marginTop:10}}><input dir={chatLocale==='en'?'ltr':'rtl'} lang={chatLocale} required maxLength={4000} style={{flex:1,padding:12}} value={input} onChange={e=>setInput(e.target.value)} placeholder={copy.placeholder}/><button disabled={busy} style={{padding:12}}>{busy?'…':copy.send}</button></form></section>
 </>}
 </main>;
}
