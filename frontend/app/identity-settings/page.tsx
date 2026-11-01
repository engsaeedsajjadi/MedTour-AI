'use client';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {useEffect,useState} from 'react';
type Status={enrolled:boolean;setup_pending:boolean};
type Setup={manual_secret:string;otp_auth_uri:string;activated:boolean};
export default function IdentitySettings(){
 const [status,setStatus]=useState<Status|null>(null);
 const [setup,setSetup]=useState<Setup|null>(null);
 const [code,setCode]=useState('');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{request<Status>('/identity/mfa/status').then(setStatus).catch(e=>setError((e as Error).message));},[]);
 async function start(){
  setBusy(true);setError('');
  try{setSetup(await request<Setup>('/identity/mfa/setup',{method:'POST'}));}
  catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function activate(){
  setBusy(true);setError('');
  try{await request('/identity/mfa/activate',{method:'POST',body:JSON.stringify({code})});
   setSetup(null);setCode('');setStatus({enrolled:true,setup_pending:false});
   setNotice('ورود دومرحله‌ای فعال شد. از ورود بعدی کد موقت لازم است. نشست‌های قبلی باطل شدند.');
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Shell title="امنیت ورود و تأیید دومرحله‌ای">
  <div className="infoBanner">احراز هویت دومرحله‌ای با کد یک‌بارمصرف برای کارکنان. کلید راه‌اندازی را در پیام‌رسان یا اسناد عمومی کپی نکنید.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:22,marginTop:16}}>
   <h2>تأیید دومرحله‌ای</h2>
   <p>وضعیت: <strong>{status?.enrolled?'فعال':'غیرفعال یا در انتظار فعال‌سازی'}</strong></p>
   {!status?.enrolled&&<div style={{display:'grid',gap:12,maxWidth:600}}>
    <button className="button" disabled={busy} onClick={()=>void start()}>شروع راه‌اندازی برنامه احراز هویت</button>
    {setup&&<>
     <p>این کلید محرمانه فقط اکنون نمایش داده می‌شود. آن را در برنامه احراز هویت با کد شش‌رقمی و بازه ۳۰ ثانیه ثبت کنید.</p>
     <code dir="ltr" style={{overflowWrap:'anywhere'}}>{setup.manual_secret}</code>
     <label>کد شش‌رقمی<input value={code} inputMode="numeric" dir="ltr" maxLength={6} pattern="[0-9]{6}" onChange={e=>setCode(e.target.value)}/></label>
     <button className="button" disabled={busy||!/^[0-9]{6}$/.test(code)} onClick={()=>void activate()}>تأیید کد و فعال‌سازی ورود دومرحله‌ای</button>
    </>}
   </div>}
   <p style={{marginTop:18}}>برای امنیت، غیرفعال‌سازی یا بازیابی بدون احراز هویت مستقل از این صفحه امکان‌پذیر نیست.</p>
  </section>
 </Shell>;
}
