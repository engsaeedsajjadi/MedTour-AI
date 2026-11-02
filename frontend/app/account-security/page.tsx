'use client';
import Shell from '@/components/Shell';
import {request,logout} from '@/lib/api';
import {useEffect,useState} from 'react';
import {fa} from '@/lib/i18n';
import QRCode from 'qrcode';
type Status={enabled:boolean;enrollment_pending:boolean;method:string;recovery_codes_configured:boolean};
type Enroll={secret:string;otpauth_uri:string;expires_in:number};
type Staff={id:string;email:string;role:string;active:boolean;auth_version:number};
export default function SecurityPage(){
 const [status,setStatus]=useState<Status|null>(null),[members,setMembers]=useState<Staff[]>([]);
 const [role,setRole]=useState('');
 const [secret,setSecret]=useState(''),[uri,setUri]=useState(''),[qr,setQr]=useState('');
 const [code,setCode]=useState(''),[pwd,setPwd]=useState(''),[newPwd,setNewPwd]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function reload(){
  const [s,me]=await Promise.all([request<Status>('/auth/mfa/status'),
   request<{role:string}>('/auth/me')]);
  setStatus(s);setRole(me.role);
  // The staff list is only reachable after the second factor is active; never let it block enrolment.
  if(me.role==='admin'&&s.enabled){
   try{setMembers((await request<{items:Staff[]}>('/auth/staff')).items);}catch{setMembers([]);}
  }
 }
 useEffect(()=>{void reload().catch(e=>setError((e as Error).message));},[]);
 // QR is drawn locally in the browser; the enrolment key never leaves this page.
 useEffect(()=>{if(!uri){setQr('');return;}
  QRCode.toDataURL(uri,{margin:1,width:220,errorCorrectionLevel:'M'}).then(setQr).catch(()=>setQr(''));},[uri]);
 async function action<T>(path:string,data?:object,method='POST'):Promise<T|null>{
  setBusy(true);setError('');setNotice('');
  try{
   const result=await request<T>(path,{method,body:data?JSON.stringify(data):undefined});
   // A failed refresh must not hide a successful action (e.g. the one-time enrolment key).
   await reload().catch(()=>{});return result;
  }catch(e){setError((e as Error).message);return null;}finally{setBusy(false);}
 }
 async function setup(){
  const result=await action<Enroll>('/auth/mfa/enroll');
  if(result){setSecret(result.secret);setUri(result.otpauth_uri);
   setNotice('کلید فقط همین بار نمایش داده می‌شود؛ آن را در برنامه احراز هویت وارد کنید و برای کسی ارسال نکنید.');}
 }
 async function confirm(){
  const result=await action<{enabled:boolean;access_token:string;refresh_token:string}>('/auth/mfa/confirm',{code});
  if(result){sessionStorage.setItem('medtour_token',result.access_token);
   sessionStorage.setItem('medtour_refresh',result.refresh_token);
   setSecret('');setUri('');setQr('');setCode('');setNotice('عامل دوم فعال و نشست‌های قبلی باطل شدند.');}
 }
 async function change(){
  const result=await action<{changed:boolean}>('/auth/password/change',{current_password:pwd,new_password:newPwd});
  if(result){setPwd('');setNewPwd('');await logout();}
 }
 return <Shell title="امنیت هویت و دسترسی">
  <div className="infoBanner">ورود دومرحله‌ای با کد یک‌بارمصرف زمان‌دار (Google Authenticator، Microsoft Authenticator یا مشابه). برای مدیران و اپراتورها اجباری است و تا فعال نشود، دسترسی به بخش‌های دیگر پنل بسته می‌ماند.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>احراز هویت دومرحله‌ای</h2>
   <p>وضعیت: <strong>{status?.enabled?'فعال':'غیرفعال'}</strong> · روش: کد یک‌بارمصرف زمان‌دار · کدهای بازیابی: ارائه نشده‌اند</p>
   {!status?.enabled&&<button className="button" disabled={busy} onClick={()=>void setup()}>ساخت کلید راه‌اندازی ورود دومرحله‌ای</button>}
   {secret&&<div style={{marginTop:15}}>
    <p>۱) در Google Authenticator یا برنامه مشابه، گزینه «اسکن کد QR» را بزنید و این کد را اسکن کنید:</p>
    {qr&&<img src={qr} width={220} height={220} alt="کد QR راه‌اندازی ورود دومرحله‌ای" style={{background:'#fff',padding:8,borderRadius:8}}/>}
    <p>اگر اسکن ممکن نیست، گزینه «وارد کردن کلید راه‌اندازی» را بزنید و این کلید را وارد کنید:</p>
    <code dir="ltr" style={{display:'block',overflowWrap:'anywhere'}}>{secret}</code>
    <p>۲) کد شش‌رقمی که برنامه نشان می‌دهد را وارد کنید:</p>
    <label>کد شش‌رقمی<input dir="ltr" type="text" inputMode="numeric"
     maxLength={6} pattern="[0-9]{6}" value={code} onChange={e=>setCode(e.target.value)}/></label>
    <button className="button" disabled={busy||!/^[0-9]{6}$/.test(code)} onClick={()=>void confirm()}>تأیید و فعال‌سازی</button>
   </div>}
  </section>
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>تغییر گذرواژه</h2>
   <label>گذرواژه فعلی<input type="password" value={pwd} onChange={e=>setPwd(e.target.value)}/></label>
   <label>گذرواژه جدید (حداقل ۱۶ کاراکتر)<input type="password" value={newPwd} onChange={e=>setNewPwd(e.target.value)}/></label>
   <button className="button" disabled={busy||newPwd.length<16||!pwd} onClick={()=>void change()}>تغییر و خروج از تمام نشست‌ها</button>
  </section>
  {role==='admin'&&<section className="panel" style={{padding:20,marginTop:18}}>
   <h2>مدیریت حساب‌های سازمان</h2>
   <div className="tableScroll"><table><thead><tr><th>حساب</th><th>نقش</th><th>وضعیت</th><th>اقدام</th></tr></thead><tbody>
    {members.map(m=><tr key={m.id}><td>{m.email}</td><td>{fa(m.role)}</td>
     <td>{m.active?'فعال':'غیرفعال'}</td>
     <td><button className="button secondary" disabled={busy} onClick={()=>void action(
      '/auth/staff/'+m.id+'/active',{active:!m.active},'PUT')}>{m.active?'غیرفعال‌کردن':'فعال‌کردن'}</button></td></tr>)}
   </tbody></table></div>
   <p>فعال‌سازی حساب، نشست‌های قبلی آن را بازیابی نمی‌کند. دسترسی پزشک به لینک فعال در بخش مدیریت پزشکان وابسته است.</p>
  </section>}
 </Shell>;
}
