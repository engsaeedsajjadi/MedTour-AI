export const API_BASE=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
export type Row=Record<string,unknown>;
export function getSession():string{if(typeof window==='undefined')return '';return sessionStorage.getItem('medtour_token')||'';}
const forget=()=>{if(typeof window!=='undefined'){sessionStorage.removeItem('medtour_token');sessionStorage.removeItem('medtour_refresh');}};
export async function logout(){const access=getSession();try{if(access)await fetch(`${API_BASE}/api/v1/auth/logout`,{method:'POST',headers:{Authorization:`Bearer ${access}`}})}catch{}finally{forget();if(typeof window!=='undefined')window.location.href='/login';}}
async function rotate():Promise<string>{if(typeof window==='undefined')throw new Error('Client session required');const previous=sessionStorage.getItem('medtour_refresh');if(!previous)throw new Error('Session expired');const res=await fetch(`${API_BASE}/api/v1/auth/refresh`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:previous}),cache:'no-store'});if(!res.ok)throw new Error('Refresh token expired');const data=await res.json();sessionStorage.setItem('medtour_token',data.access_token);sessionStorage.setItem('medtour_refresh',data.refresh_token);return data.access_token;}
let inFlight:Promise<string>|null=null;
export async function request<T=unknown>(path:string,options:RequestInit={}):Promise<T>{
 const token=getSession();if(!token)throw new Error('ابتدا وارد حساب شوید.');
 async function send(credential:string){return fetch(`${API_BASE}/api/v1${path}`,{...options,cache:'no-store',headers:{'Content-Type':'application/json',Authorization:`Bearer ${credential}`,...options.headers}})}
 let result=await send(token);
 if(result.status===401){try{if(!inFlight)inFlight=rotate().finally(()=>{inFlight=null});const newToken=await inFlight;result=await send(newToken);}catch{forget();if(typeof window!=='undefined')window.location.href='/login';throw new Error('نشست شما منقضی شده است.');}}
 const data=await result.json().catch(()=>({detail:result.statusText}));
 if(!result.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${result.status}`);
 return data as T;
}

/** Authenticated binary download with the same refresh-token contract as request(). */
export async function downloadPdf(path:string,filename:string):Promise<void>{
 const initial=getSession();
 if(!initial)throw new Error('ابتدا وارد حساب شوید.');
 const load=(token:string)=>fetch(`${API_BASE}/api/v1${path}`,{
  method:'GET',headers:{Authorization:`Bearer ${token}`},cache:'no-store'
 });
 let response=await load(initial);
 if(response.status===401){
  try{
   if(!inFlight)inFlight=rotate().finally(()=>{inFlight=null});
   response=await load(await inFlight);
  }catch{forget();throw new Error('نشست شما منقضی شده است.');}
 }
 if(!response.ok){
  const body=await response.json().catch(()=>({detail:'دریافت سند ناموفق بود.'}));
  throw new Error(typeof body.detail==='string'?body.detail:'HTTP '+response.status);
 }
 const mime=response.headers.get('content-type')||'';
 if(!mime.includes('application/pdf'))throw new Error('فرمت پاسخ PDF نیست.');
 const blob=await response.blob();
 if(blob.size>5_000_000)throw new Error('اندازه PDF بیش از حد مجاز است.');
 const url=URL.createObjectURL(blob);
 try{
  const anchor=document.createElement('a');anchor.href=url;anchor.download=filename;
  document.body.appendChild(anchor);anchor.click();anchor.remove();
 }finally{setTimeout(()=>URL.revokeObjectURL(url),1000)}
}
