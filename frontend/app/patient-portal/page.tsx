'use client';
import {useEffect,useState} from 'react';
import {API_BASE} from '@/lib/api';
type Journey={case_id:string,status:string,specialty:string,services:{service:string,status:string}[],confirmed_appointments:{at:string,reference:string}[],approved_quotes:{amount_minor:number,currency:string,id:string}[]};
type ChatMessage={sender:string,body:string,language:string};
export default function PatientPortal(){
 const [token,setToken]=useState(''),[patient,setPatient]=useState<{name:string,language:string}|null>(null),[journey,setJourney]=useState<Journey[]>([]);
 const [messages,setMessages]=useState<ChatMessage[]>([]),[input,setInput]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
   const hash=window.location.hash.slice(1);const code=hash.startsWith('access=')?decodeURIComponent(hash.slice(7)):'';
   if(code){sessionStorage.setItem('medtour_patient_access',code);window.history.replaceState({},'',window.location.pathname);}
   setToken(code||sessionStorage.getItem('medtour_patient_access')||'');
 },[]);
 async function call<T>(path:string,init:RequestInit={}):Promise<T>{const r=await fetch(`${API_BASE}/api/v1/portal${path}`,{...init,headers:{'Content-Type':'application/json','X-Patient-Access':token,...init.headers},cache:'no-store'});const data=await r.json();if(!r.ok)throw new Error(String(data.detail||'Request failed'));return data as T;}
 useEffect(()=>{if(!token)return;Promise.all([call<{name:string,language:string}>('/me'),call<Journey[]>('/journey'),call<ChatMessage[]>('/chat')]).then(([p,j,m])=>{setPatient(p);setJourney(j);setMessages(m)}).catch(e=>setError(e.message));},[token]);
 async function send(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const result=await call<{warning:string|null,human_handoff:boolean}>('/chat',{method:'POST',body:JSON.stringify({message:input,language:patient?.language||'en'})});setMessages(await call<ChatMessage[]>('/chat'));setInput('');if(result.warning)setError(result.warning);else if(result.human_handoff)setError('Conversation transferred to a human coordinator.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const logout=()=>{sessionStorage.removeItem('medtour_patient_access');setToken('');setPatient(null);setJourney([]);setMessages([])};
 return <main style={{maxWidth:900,margin:'32px auto',padding:24,fontFamily:'system-ui',color:'#142b3c'}}>
 <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12}}><h1>✚ MedTour AI | Patient Portal</h1><button onClick={logout}>Clear access</button></header>
 <p>Secure coordination portal · بوابة المريض · پورتال بیمار</p><p>Information shown here is for administrative coordination; emergency care and clinical decisions require qualified local services.</p>
 {error&&<div role="alert" style={{background:'#ffefdd',padding:16,borderRadius:10}}>{error}</div>}
 {!patient?<p>Open the short-lived private link provided by your coordinator. Do not share it.</p>:<><h2>{patient.name}</h2>
 {journey.map(c=><section key={c.case_id} style={{border:'1px solid #cedae0',padding:20,margin:'16px 0',borderRadius:12}}><h3>Medical case · {c.specialty||'Medical service'} — {c.status}</h3>
 <small>Reference: {c.case_id}</small><h4>Travel and care coordination</h4>{c.services.length===0?<p>No active services.</p>:c.services.map((s,i)=><p key={i}>{s.service} — {s.status}</p>)}
 <h4>Confirmed appointments</h4>{c.confirmed_appointments.map((a,i)=><p key={i}>{a.at} — {a.reference}</p>)}
 <h4>Approved estimates</h4>{c.approved_quotes.map(q=><p key={q.id}>{q.amount_minor} minor units / {q.currency}</p>)}</section>)}
 <section style={{border:'1px solid #cedae0',padding:20,borderRadius:12}}><h3>Secure coordination chat</h3><p>Messages may be reviewed by a human coordinator. Do not use for emergencies.</p><div style={{maxHeight:390,overflowY:'auto',background:'#f6f9fb',padding:16,borderRadius:8}}>{messages.map((m,i)=><div key={i} style={{padding:10,margin:'8px 0',background:'#fff',borderRadius:8}}><small>{m.sender}</small><div dir="auto">{m.body}</div></div>)}</div><form onSubmit={send} style={{display:'flex',gap:8,marginTop:10}}><input required maxLength={4000} style={{flex:1,padding:12}} value={input} onChange={e=>setInput(e.target.value)} placeholder="Message your coordinator"/><button disabled={busy} style={{padding:12}}>{busy?'Sending…':'Send'}</button></form></section>
 </>}
 </main>;
}
