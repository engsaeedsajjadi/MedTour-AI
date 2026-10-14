export const API_BASE=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
export type Row=Record<string,unknown>;
export function getSession():string{if(typeof window==='undefined')return '';return sessionStorage.getItem('medtour_token')||'';}
export function logout(){if(typeof window!=='undefined'){sessionStorage.removeItem('medtour_token');window.location.href='/login';}}
export async function request<T=unknown>(path:string,options:RequestInit={}):Promise<T>{
 const token=getSession();
 if(!token)throw new Error('ابتدا وارد حساب شوید.');
 const result=await fetch(`${API_BASE}/api/v1${path}`,{
   ...options,cache:'no-store',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,...options.headers}
 });
 const data=await result.json().catch(()=>({detail:result.statusText}));
 if(result.status===401){logout();throw new Error('نشست شما منقضی شده است.');}
 if(!result.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${result.status}`);
 return data as T;
}
