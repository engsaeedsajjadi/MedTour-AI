'use client';
import {API_BASE} from '@/lib/api';
import {useEffect,useState} from 'react';
const description:Record<string,string>={
 intake:'Collect initial non-diagnostic health service inquiry details.',
 medical_documents:'Receive and securely store medical files for qualified review.',
 communication:'Contact you about administrative treatment coordination.',
 ai_processing:'Use an approved AI processor to assist administrative translation and document summaries.'
};
type Preview={purpose:string;privacy_notice_url:string|null;privacy_notice_version:string;production_notice_configured:boolean};
export default function Consent(){
 const [token,setToken]=useState(''),[data,setData]=useState<Preview|null>(null),[choice,setChoice]=useState(false),[result,setResult]=useState(''),[error,setError]=useState('');
 useEffect(()=>{const frag=window.location.hash.slice(1);const params=new URLSearchParams(frag);const key=params.get('token')||'';window.history.replaceState({},'',window.location.pathname);setToken(key);if(!key)return;
 fetch(`${API_BASE}/api/v1/consent-links/preview?token=${encodeURIComponent(key)}`,{cache:'no-store'}).then(async r=>{const v=await r.json();if(!r.ok)throw new Error(v.detail||'Link expired');return v}).then(setData).catch(e=>setError((e as Error).message));},[]);
 async function respond(accepted:boolean){setError('');setResult('');if(!data)return;try{const r=await fetch(`${API_BASE}/api/v1/consent-links/respond`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,notice_version:data.privacy_notice_version,accepted})});const v=await r.json();if(!r.ok)throw new Error(v.detail||'Unable to save');setResult(accepted?'Consent recorded. You may close this page.':'Declined. You may close this page.');setToken('');setData(null)}catch(e){setError((e as Error).message)}}
 return <main dir="auto" style={{margin:'6vh auto',maxWidth:650,padding:28,fontFamily:'system-ui, sans-serif',border:'1px solid #dbe6ea',borderRadius:14}}>
 <h1>MedTour AI | Privacy consent</h1><p>Required for confidential international patient coordination. This is not a medical diagnosis or an emergency service.</p>
 {error&&<p role="alert" style={{color:'#a93434'}}>{error}</p>}{result&&<p role="status">{result}</p>}
 {data&&<><h2>{data.purpose}</h2><p>{description[data.purpose]||'Purpose-specific data processing'}</p>
 <p>Notice version: {data.privacy_notice_version}</p>
 {data.privacy_notice_url?<p><a href={data.privacy_notice_url} target="_blank" rel="noopener noreferrer">Read the privacy notice before deciding</a></p>:<p style={{color:'#9a6500'}}>Development environment: final legal privacy notice is not configured. Do not use with real patients.</p>}
 <label style={{display:'block',margin:'22px 0'}}><input type="checkbox" checked={choice} onChange={e=>setChoice(e.target.checked)}/> I have read the notice and I agree to this specific purpose.</label>
 <div style={{display:'flex',gap:12}}><button disabled={!choice} onClick={()=>respond(true)}>I agree</button><button onClick={()=>respond(false)}>Decline</button></div></>}
 {!token&&!data&&!result&&<p>A private consent invitation link is required.</p>}
 </main>
}
