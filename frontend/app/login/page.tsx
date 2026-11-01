'use client';
import {useState} from 'react';
import {API_BASE} from '@/lib/api';
import {faError,faNetwork} from '@/lib/i18n';
import {homeFor} from '@/lib/roles';
type Tokens={access_token:string;refresh_token:string;role:string};
type Challenge={mfa_required:true;challenge_token:string;expires_in:number};
export default function Login(){
 const [tenant,setTenant]=useState('medtour-local'),[email,setEmail]=useState(''),[password,setPassword]=useState('');
 const [otp,setOtp]=useState(''),[challenge,setChallenge]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 function enter(t:Tokens){
  sessionStorage.setItem('medtour_tenant_slug',tenant);
  sessionStorage.setItem('medtour_token',t.access_token);
  sessionStorage.setItem('medtour_refresh',t.refresh_token);
  window.location.replace(homeFor(String(t.role)));
 }
 async function submit(e:React.FormEvent){
  e.preventDefault();setBusy(true);setError('');
  try{
   const endpoint=challenge?'/api/v1/auth/mfa/verify':'/api/v1/auth/login';
   const payload=challenge?{challenge_token:challenge,code:otp}:{tenant_slug:tenant,email,password};
   let res:Response;
   try{res=await fetch(API_BASE+endpoint,{method:'POST',
    headers:{'Content-Type':'application/json'},cache:'no-store',
    body:JSON.stringify(payload)});}catch(err){throw Error(faNetwork(err));}
   const data=await res.json().catch(()=>({}));
   if(!res.ok)throw Error(faError(data.detail,res.status));
   if(data.mfa_required){
    setChallenge((data as Challenge).challenge_token);setPassword('');return;
   }
   if(!data.access_token||!data.refresh_token)throw Error('پاسخ ورود نامعتبر است');
   enter(data as Tokens);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <div className="loginScreen">
  <div className="loginAside"><div className="loginLogo">✚</div>
   <div className="eyebrow">مدیریت بیماران بین‌المللی</div>
   <h1>مراقبت هوشمند،<em> فراتر از مرزها.</em></h1>
   <p>سامانه هماهنگی درمان و سفر با کنترل دسترسی کارکنان.</p>
   <div className="languageRow">فارسی <span>•</span> عربی <span>•</span> انگلیسی <span>•</span> پشتو <span>•</span> دری</div>
  </div>
  <div className="loginContent"><div className="loginCard">
   <small>MedTour AI · ورود کارکنان</small>
   <h2>{challenge?'مرحله دوم احراز هویت':'ورود به سامانه'}</h2>
   <form onSubmit={submit}>
    {!challenge?<>
     <label>شناسه سازمان<input required dir="ltr" autoComplete="organization" value={tenant} onChange={e=>setTenant(e.target.value)}/></label>
     <label>ایمیل<input required type="email" dir="ltr" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)}/></label>
     <label>رمز عبور<input required type="password" dir="ltr" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
    </>:<>
     <p>کد شش‌رقمی فعلی برنامه احراز هویت خود را وارد کنید. چالش به مدت پنج دقیقه معتبر است.</p>
     <label>کد احراز هویت<input required type="text" dir="ltr" value={otp} inputMode="numeric"
      pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" onChange={e=>setOtp(e.target.value)}/></label>
    </>}
    {error&&<div role="alert" className="errorBox">{error}</div>}
    <button disabled={busy} className="button full">{busy?'در حال بررسی…':challenge?'تأیید کد دوم':'ورود به پنل'}</button>
    {challenge&&<button type="button" className="button secondary" onClick={()=>{
     setChallenge('');setOtp('');setError('');}}>شروع دوباره ورود</button>}
   </form><div className="securityNote">🔒 نسخه نمایشی؛ فقط با داده ساختگی استفاده شود.</div>
  </div></div>
 </div>;
}
