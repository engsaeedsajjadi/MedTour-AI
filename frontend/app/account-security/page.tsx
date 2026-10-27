'use client';
import Shell from '@/components/Shell';
import {request,logout} from '@/lib/api';
import {useEffect,useState} from 'react';
type Status={enabled:boolean;enrollment_pending:boolean;method:string;recovery_codes_configured:boolean};
type Enroll={secret:string;otpauth_uri:string;expires_in:number};
type Staff={id:string;email:string;role:string;active:boolean;auth_version:number};
export default function SecurityPage(){
 const [status,setStatus]=useState<Status|null>(null),[members,setMembers]=useState<Staff[]>([]);
 const [role,setRole]=useState('');
 const [secret,setSecret]=useState(''),[uri,setUri]=useState('');
 const [code,setCode]=useState(''),[pwd,setPwd]=useState(''),[newPwd,setNewPwd]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function reload(){
  const [s,me]=await Promise.all([request<Status>('/auth/mfa/status'),
   request<{role:string}>('/auth/me')]);
  setStatus(s);setRole(me.role);
  if(me.role==='admin')setMembers((await request<{items:Staff[]}>('/auth/staff')).items);
 }
 useEffect(()=>{void reload().catch(e=>setError((e as Error).message));},[]);
 async function action<T>(path:string,data?:object,method='POST'):Promise<T|null>{
  setBusy(true);setError('');setNotice('');
  try{
   const result=await request<T>(path,{method,body:data?JSON.stringify(data):undefined});
   await reload();return result;
  }catch(e){setError((e as Error).message);return null;}finally{setBusy(false);}
 }
 async function setup(){
  const result=await action<Enroll>('/auth/mfa/enroll');
  if(result){setSecret(result.secret);setUri(result.otpauth_uri);
   setNotice('کلید فقط همین بار نمایش داده می‌شود؛ آن را در برنامه TOTP وارد کنید. از انتشار یا ارسال آن خودداری کنید.');}
 }
 async function confirm(){
  const result=await action<{enabled:boolean;access_token:string;refresh_token:string}>('/auth/mfa/confirm',{code});
  if(result){sessionStorage.setItem('medtour_token',result.access_token);
   sessionStorage.setItem('medtour_refresh',result.refresh_token);
   setSecret('');setUri('');setCode('');setNotice('عامل دوم فعال و نشست‌های قبلی باطل شدند.');}
 }
 async function change(){
  const result=await action<{changed:boolean}>('/auth/password/change',{current_password:pwd,new_password:newPwd});
  if(result){setPwd('');setNewPwd('');await logout();}
 }
 return <Shell title="امنیت هویت و دسترسی">
  <div className="infoBanner">بخش ۲۷ — TOTP برای حساب کارکنان. این نسخه برای محیط آزمایشی است؛ بدون کلید مستقل رمزگذاری MFA قابل فعال‌سازی نیست و اتصال MFA به Gateway آزمایشی بخش ۲۶ هنوز برای همه مسیرها کامل نشده است.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>احراز هویت دومرحله‌ای</h2>
   <p>وضعیت: <strong>{status?.enabled?'فعال':'غیرفعال'}</strong> · روش: TOTP · کدهای بازیابی: ارائه نشده‌اند</p>
   {!status?.enabled&&<button className="button" disabled={busy} onClick={()=>void setup()}>ساخت کلید راه‌اندازی TOTP</button>}
   {secret&&<div style={{marginTop:15}}>
    <p>کلید محرمانه برای افزودن دستی به اپ Authenticator:</p>
    <code dir="ltr" style={{display:'block',overflowWrap:'anywhere'}}>{secret}</code>
    <p>می‌توانید با برنامه Authenticator، پیوند زیر را نیز باز کنید:</p>
    <code dir="ltr" style={{display:'block',overflowWrap:'anywhere'}}>{uri}</code>
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
    {members.map(m=><tr key={m.id}><td>{m.email}</td><td>{m.role}</td>
     <td>{m.active?'فعال':'غیرفعال'}</td>
     <td><button className="button secondary" disabled={busy} onClick={()=>void action(
      '/auth/staff/'+m.id+'/active',{active:!m.active},'PUT')}>{m.active?'غیرفعال‌کردن':'فعال‌کردن'}</button></td></tr>)}
   </tbody></table></div>
   <p>فعال‌سازی حساب، نشست‌های قبلی آن را بازیابی نمی‌کند. دسترسی پزشک به لینک فعال در بخش مدیریت پزشکان وابسته است.</p>
  </section>}
 </Shell>;
}
