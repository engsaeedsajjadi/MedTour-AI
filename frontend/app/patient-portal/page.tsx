'use client';
import {useEffect,useState} from 'react';
import {API_BASE} from '@/lib/api';
import {fa,faError,faNetwork,tone} from '@/lib/i18n';
type Journey={case_id:string,status:string,specialty:string,services:{service:string,status:string}[],confirmed_appointments:{at:string,reference:string}[],approved_quotes:{amount_minor:number,currency:string,id:string}[],travel?:Travel};
type Travel={visa:{status:string,visa_type:string,decision:string|null,intended_departure_at:string|null,issued_reported:boolean}[],
 accommodation:{hotel:string,city:string,check_in:string,check_out:string,room_type:string,guests:number,status:string,confirmed:boolean}[],
 transfers:{kind:string,starts_at:string,ends_at:string,from:string,to:string,passengers:number,status:string,confirmed:boolean}[],
 readiness:{ready_to_travel:boolean,pending:string[],departure_at:string|null}};
type Org={privacy_notice_version:string,display_name:string,contact_email:string,contact_phone:string,website:string,privacy_notice_url:string,patient_support_hours:string};
type ChatMessage={sender:string,body:string,language:string};

const LANGUAGE_LABELS:Record<string,string>={fa:'فارسی',ar:'العربية',en:'English',ps:'پښتو',prs:'دری'};
const CHAT_UI:Record<string,{chat:string,placeholder:string,send:string,handoff:string,intake:string,answer:string,notice:string,language:string}>={
 fa:{chat:'گفتگوی امن هماهنگی',placeholder:'پیام برای هماهنگ‌کننده',send:'ارسال',handoff:'گفتگو به هماهنگ‌کننده انسانی ارجاع شده است.',intake:'فرم پذیرش',answer:'ثبت پاسخ',notice:'این سامانه خدمات اورژانس یا تشخیص ارائه نمی‌کند.',language:'زبان گفتگو'},
 ar:{chat:'محادثة التنسيق الآمنة',placeholder:'رسالة إلى المنسق',send:'إرسال',handoff:'تم تحويل المحادثة إلى منسق بشري.',intake:'استمارة الاستقبال',answer:'حفظ الإجابة',notice:'هذه الخدمة ليست للطوارئ أو التشخيص.',language:'لغة المحادثة'},
 en:{chat:'Secure coordination chat',placeholder:'Message your coordinator',send:'Send',handoff:'Conversation transferred to a human coordinator.',intake:'Intake form',answer:'Save answer',notice:'This service cannot provide emergency care or diagnosis.',language:'Conversation language'},
 ps:{chat:'خوندي اداري خبرې',placeholder:'همغږي کوونکي ته پیغام',send:'لېږل',handoff:'ستاسو خبرې انساني همغږي کوونکي ته وسپارل شوې.',intake:'د منلو فورمه',answer:'ځواب ثبت کړئ',notice:'دا خدمت بیړنۍ پاملرنه یا تشخیص نه وړاندې کوي.',language:'د خبرو ژبه'},
 prs:{chat:'گفتگوی مصون هماهنگی',placeholder:'پیام به هماهنگ‌کننده',send:'ارسال',handoff:'گفتگو به هماهنگ‌کننده انسانی راجع شد.',intake:'فورم پذیرش',answer:'ثبت جواب',notice:'این خدمت برای حالت عاجل یا تشخیص طبی نیست.',language:'زبان گفتگو'}
};
const SENDER:Record<string,string>={patient:'شما',staff:'هماهنگ‌کننده',coordinator:'هماهنگ‌کننده',assistant:'دستیار',system:'سامانه'};

function readInvite():string{
 const hash=window.location.hash.slice(1);
 return hash.startsWith('invite=')?decodeURIComponent(hash.slice(7)):'';
}
function money(minor:number,currency:string){const digits=['IRR','JPY','KRW','IQD','AFN'].includes(currency)?0:2;return (minor/10**digits).toLocaleString('fa-IR',{minimumFractionDigits:digits,maximumFractionDigits:digits})+' '+currency;}
const PENDING_LABEL:Record<string,string>={appointment:'تأیید نوبت پزشک',quote:'تأیید برآورد هزینه',visa:'صدور ویزای درمانی',accommodation:'تأیید رزرو هتل',transfer:'تأیید ترانسفر فرودگاهی',case_approval:'تأیید نهایی پرونده توسط هماهنگ‌کننده'};
const ZONE:Record<string,string>={airport:'فرودگاه',hotel:'هتل',hospital:'بیمارستان',city_center:'مرکز شهر',not_applicable:'—'};
const ROOM:Record<string,string>={single:'یک‌تخته',double:'دوتخته',accessible:'مناسب معلولان'};
function fmtDay(value:string){const d=new Date(value+(value.length===10?'T00:00:00':''));return Number.isNaN(d.getTime())?value:d.toLocaleDateString('fa-IR',{dateStyle:'full'});}
function TripPlan({t}:{t:Travel}){
 const r=t.readiness;
 return <div className="portalBox tripPlan">
  {r.ready_to_travel?<div className="readyBanner" role="status"><h3>✅ سفر شما آماده است</h3>
   <p>نوبت پزشک، برآورد هزینه{t.visa.length?'، ویزای درمانی':''}، هتل{t.transfers.length?' و ترانسفر فرودگاهی':''} برای شما تأیید شده است. جزئیات را پایین ببینید.</p>
   <p className="subtle">پیش از حرکت: گذرنامه معتبر (حداقل ۶ ماه اعتبار)، ویزا و اصل مدارک پزشکی را همراه داشته باشید. برای هر تغییری از گفتگوی امن همین پرتال با هماهنگ‌کننده در تماس باشید. این تأییدها توسط هماهنگ‌کننده ثبت شده‌اند؛ تأییدیه اصلی هر ارائه‌دهنده را نیز نگه دارید.</p></div>
  :<div className="pendingBanner" role="status"><h3>سفر شما در حال آماده‌سازی است</h3><p>موارد باقی‌مانده:</p><ul>{r.pending.map(k=><li key={k}>{PENDING_LABEL[k]||fa(k)}</li>)}</ul></div>}
  <div className="portalGrid">
   <div><h3>ویزای درمانی</h3>{t.visa.length===0?<p className="subtle">درخواست ویزا ثبت نشده است.</p>:t.visa.map((v,i)=><p key={i}><span className={'badge '+(v.issued_reported?'good':tone(v.status))}>{v.issued_reported?'صادر شد':fa(v.decision||v.status)}</span>{v.intended_departure_at&&<><br/>تاریخ حرکت: {fmtDate(v.intended_departure_at)}</>}</p>)}</div>
   <div><h3>اقامت</h3>{t.accommodation.length===0?<p className="subtle">هتلی رزرو نشده است.</p>:t.accommodation.map((h,i)=><p key={i}><strong dir="auto">{h.hotel}</strong> — {h.city}<br/>ورود: {fmtDay(h.check_in)}<br/>خروج: {fmtDay(h.check_out)}<br/>اتاق {ROOM[h.room_type]||h.room_type} · {h.guests.toLocaleString('fa-IR')} نفر <span className={'badge '+(h.confirmed?'good':tone(h.status))}>{h.confirmed?'تأیید شده':fa(h.status)}</span></p>)}</div>
   <div><h3>ترانسفر</h3>{t.transfers.length===0?<p className="subtle">ترانسفری ثبت نشده است.</p>:t.transfers.map((x,i)=><p key={i}>{fa(x.kind)}: {ZONE[x.from]||x.from} ← {ZONE[x.to]||x.to}<br/>{fmtDate(x.starts_at)} · {x.passengers.toLocaleString('fa-IR')} نفر <span className={'badge '+(x.confirmed?'good':tone(x.status))}>{x.confirmed?'تأیید شده':fa(x.status)}</span></p>)}</div>
  </div>
 </div>;
}
function fmtDate(value:string){const d=new Date(value);return Number.isNaN(d.getTime())?value:d.toLocaleString('fa-IR',{dateStyle:'medium',timeStyle:'short'});}

export default function PatientPortal(){
 const [invite,setInvite]=useState(''),[otp,setOtp]=useState(''),[otpBusy,setOtpBusy]=useState(false);
 const [org,setOrg]=useState<Org|null>(null);
 const [consents,setConsents]=useState<Record<string,boolean>>({});
 const [token,setToken]=useState(''),[patient,setPatient]=useState<{name:string,language:string}|null>(null),[journey,setJourney]=useState<Journey[]>([]);
 const [intake,setIntake]=useState<{id:string;case_id:string;status:string;next_prompt:string|null;language:string;stage:number}|null>(null);
 const [intakeAnswer,setIntakeAnswer]=useState('');
 const [documentFile,setDocumentFile]=useState<File|null>(null);
 const [documentStatus,setDocumentStatus]=useState('');
 const [documentsByCase,setDocumentsByCase]=useState<Record<string,Array<{id:string;filename:string;status:string}>>>({});
 const [chatLocale,setChatLocale]=useState('fa');
 const copy=CHAT_UI[chatLocale]||CHAT_UI.fa;
 const [messages,setMessages]=useState<ChatMessage[]>([]),[input,setInput]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  // Legacy access tokens are never accepted from the URL; a session only comes from a verified OTP exchange.
  function takeInvite(){
   const invitation=readInvite();
   if(invitation){sessionStorage.setItem('medtour_patient_invite',invitation);window.history.replaceState({},'',window.location.pathname);}
   setInvite(invitation||sessionStorage.getItem('medtour_patient_invite')||'');
  }
  takeInvite();
  setToken(sessionStorage.getItem('medtour_patient_access')||'');
  window.addEventListener('hashchange',takeInvite);
  return ()=>window.removeEventListener('hashchange',takeInvite);
 },[]);
 async function call<T>(path:string,init:RequestInit={}):Promise<T>{
  let r:Response;
  try{r=await fetch(`${API_BASE}/api/v1/portal${path}`,{...init,headers:{'Content-Type':'application/json','X-Patient-Access':token,...init.headers},cache:'no-store'});}
  catch(e){throw new Error(faNetwork(e));}
  const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(faError(data.detail,r.status));return data as T;
 }
 useEffect(()=>{if(!token)return;Promise.all([call<{name:string,language:string}>('/me'),call<Journey[]>('/journey'),call<ChatMessage[]>('/chat'),call<{purposes:Record<string,boolean>}>('/consents')]).then(([p,j,m,co])=>{setPatient(p);setChatLocale(CHAT_UI[p.language]?p.language:'fa');setJourney(j);setMessages(m);setConsents(co.purposes);call<Org>('/organization').then(setOrg).catch(()=>{})}).catch(e=>{setError(e.message);sessionStorage.removeItem('medtour_patient_access');setToken('');setPatient(null);});
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[token]);
 async function send(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setNotice('');try{const result=await call<{warning:string|null,human_handoff:boolean,handoff_notice?:string|null}>('/chat',{method:'POST',body:JSON.stringify({message:input,language:chatLocale})});setMessages(await call<ChatMessage[]>('/chat'));setInput('');if(result.warning)setNotice(result.warning);else if(result.human_handoff)setNotice(result.handoff_notice||copy.handoff)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function startIntake(caseId:string){setBusy(true);setError('');try{setIntake(await call<NonNullable<typeof intake>>('/intake/sessions',{method:'POST',body:JSON.stringify({case_id:caseId,language:chatLocale})}));}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function answerIntake(e:React.FormEvent){e.preventDefault();if(!intake)return;setBusy(true);setError('');try{const out=await call<typeof intake&{warning?:string}>(`/intake/sessions/${intake.id}/answer`,{method:'POST',body:JSON.stringify({answer:intakeAnswer})});setIntake(out);setIntakeAnswer('');if(out.warning)setNotice(out.warning);}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function loadDocuments(caseId:string){
  setError('');
  try{
   const r=await fetch(API_BASE+'/api/v1/secure-documents/portal/cases/'+encodeURIComponent(caseId)+'/list',{headers:{'X-Patient-Access':token},cache:'no-store'});
   if(!r.ok){const body=await r.json().catch(()=>({}));throw new Error(faError(body.detail,r.status));}
   const docs=await r.json() as Array<{id:string;filename:string;status:string}>;
   setDocumentsByCase(prev=>({...prev,[caseId]:docs}));
  }catch(e){setError(faNetwork(e))}
 }
 async function downloadDocument(caseId:string,id:string){
  setBusy(true);setError('');
  try{
   const r=await fetch(API_BASE+'/api/v1/secure-documents/portal/cases/'+encodeURIComponent(caseId)+'/documents/'+encodeURIComponent(id),{headers:{'X-Patient-Access':token},cache:'no-store'});
   if(!r.ok){const body=await r.json().catch(()=>({}));throw new Error(faError(body.detail,r.status));}
   const obj=URL.createObjectURL(await r.blob());
   const link=document.createElement('a');link.href=obj;link.download='medical-document';
   document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(obj),1000);
  }catch(e){setError(faNetwork(e))}finally{setBusy(false)}
 }
 async function uploadDocument(caseId:string){if(!documentFile)return;setBusy(true);setDocumentStatus('');setError('');try{const body=new FormData();body.append('file',documentFile);const r=await fetch(`${API_BASE}/api/v1/secure-documents/portal/cases/${caseId}`,{method:'POST',headers:{'X-Patient-Access':token},body,cache:'no-store'});const result=await r.json().catch(()=>({}));if(!r.ok)throw new Error(faError(result.detail,r.status));setDocumentStatus('فایل ثبت شد · وضعیت: '+fa(result.status));setDocumentFile(null);await loadDocuments(caseId);}catch(e){setError(faNetwork(e))}finally{setBusy(false)}}
 async function redeem(e:React.FormEvent){e.preventDefault();setOtpBusy(true);setError('');
  try{
   const response=await fetch(API_BASE+'/api/v1/portal/session/exchange',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({invitation_token:invite,verification_code:otp}),cache:'no-store'});
   const body=await response.json().catch(()=>({}));if(!response.ok)throw new Error(faError(body.detail,response.status));
   sessionStorage.removeItem('medtour_patient_invite');sessionStorage.setItem('medtour_patient_access',body.access_token);
   setInvite('');setOtp('');setNotice('');setToken(body.access_token);
  }catch(e){setError(faNetwork(e));}finally{setOtpBusy(false);}
 }
 async function changeConsent(purpose:string,accepted:boolean){
  if(!accepted&&!window.confirm('با لغو این رضایت، نشست شما بسته می‌شود و برای ورود دوباره به دعوت جدید نیاز دارید. ادامه می‌دهید؟'))return;
  setBusy(true);setError('');
  try{
   await call('/consents',{method:'POST',body:JSON.stringify({purpose,accepted,notice_version:org?.privacy_notice_version||'v1'})});
   if(!accepted){await logout();setNotice('رضایت لغو و نشست بسته شد. برای دسترسی دوباره دعوت جدید لازم است.');}
   else setConsents(x=>({...x,[purpose]:true}));
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function logout(){
  const t=token;
  sessionStorage.removeItem('medtour_patient_access');sessionStorage.removeItem('medtour_patient_invite');
  setToken('');setInvite('');setOtp('');setPatient(null);setOrg(null);setJourney([]);setMessages([]);setDocumentsByCase({});setConsents({});setIntake(null);
  if(t)try{await fetch(API_BASE+'/api/v1/portal/session/logout',{method:'POST',headers:{'X-Patient-Access':t},cache:'no-store'});}catch{}
 }
 return <main className="portal">
  <header className="portalHeader">
   <div className="publicBrand"><span className="brandMark" aria-hidden="true">✚</span><div><strong dir="auto">{org?.display_name||'MedTour AI'}</strong><small>پرتال امن بیمار</small></div></div>
   {patient&&<button className="logout" onClick={logout}>خروج از پرتال</button>}
  </header>
  <div className="infoBanner">اطلاعات این پرتال برای هماهنگی اداری است. در شرایط اورژانسی و برای تصمیم‌های درمانی با مراکز درمانی مجاز محل خود تماس بگیرید.</div>
  {error&&<div role="alert" className="errorBox">{error}</div>}
  {notice&&<div role="status" className="successBox">{notice}</div>}
  {!patient?<section className="panel portalPanel">
   <h2>ورود به پرتال</h2>
   <p className="subtle">لینک دعوت و کد شش‌رقمی را از هماهنگ‌کننده دریافت می‌کنید. لینک دعوت به‌تنهایی اجازه مشاهده پرونده نمی‌دهد.</p>
   <form onSubmit={redeem} className="portalForm">
    <label>کد دعوت<input required dir="ltr" value={invite} onChange={e=>setInvite(e.target.value)} placeholder="از لینک دعوت به‌صورت خودکار پر می‌شود"/></label>
    <label>کد شش‌رقمی<input required dir="ltr" inputMode="numeric" maxLength={6} pattern="[0-9]{6}" autoComplete="one-time-code" value={otp} onChange={e=>setOtp(e.target.value)}/></label>
    <button className="button" disabled={otpBusy||invite.length<35||otp.length!==6}>{otpBusy?'در حال بررسی…':'ورود با کد یک‌بارمصرف'}</button>
   </form>
   <p className="subtle">هر دعوت ۱۰ دقیقه و حداکثر ۵ تلاش اعتبار دارد.</p>
  </section>:<>
   <h1 className="portalName" dir="auto">{patient.name}</h1>
   {org&&(org.contact_email||org.contact_phone||org.privacy_notice_url)&&<section className="panel portalPanel portalContact">
    <h2>تماس با {org.display_name}</h2>
    {org.contact_phone&&<p>تلفن: <a dir="ltr" href={'tel:'+org.contact_phone.replace(/[^0-9+]/g,'')}>{org.contact_phone}</a></p>}
    {org.contact_email&&<p>ایمیل: <a dir="ltr" href={'mailto:'+org.contact_email}>{org.contact_email}</a></p>}
    {org.patient_support_hours&&<p className="subtle">ساعات پاسخ‌گویی: {org.patient_support_hours}</p>}
    {org.privacy_notice_url&&<p><a href={org.privacy_notice_url} target="_blank" rel="noopener noreferrer">اطلاعیه حریم خصوصی</a></p>}
   </section>}
   <section className="panel portalPanel">
    <h2>رضایت‌های من</h2>
    <p className="subtle">هر تغییر ثبت می‌شود. لغو هر رضایت، نشست فعلی را می‌بندد.</p>
    {org?.privacy_notice_url&&<p><a className="textLink" href={org.privacy_notice_url} target="_blank" rel="noopener noreferrer">پیش از تصمیم، اطلاعیه حریم خصوصی را بخوانید</a></p>}
    <div className="consentList">{Object.entries(consents).map(([purpose,accepted])=><div key={purpose} className="consentRow">
     <span>{fa(purpose)}</span>
     <span className={'badge '+(accepted?'':'muted')}>{accepted?'فعال':'غیرفعال'}</span>
     <button className={accepted?'button secondary':'button'} disabled={busy} onClick={()=>void changeConsent(purpose,!accepted)}>{accepted?'لغو رضایت':'اعطای رضایت'}</button>
    </div>)}</div>
   </section>
   {journey.map(c=><section key={c.case_id} className="panel portalPanel">
    <div className="portalCaseHead"><h2>پرونده {fa(c.specialty)||'درمانی'}</h2><span className={'badge '+tone(c.status)}>{fa(c.status)}</span></div>
    <p className="subtle">شماره پیگیری: <code>{c.case_id.slice(0,8)}</code></p>
    <p><button className="button secondary" disabled={busy} onClick={()=>startIntake(c.case_id)}>شروع یا ادامه فرم پذیرش</button></p>
    <div className="portalBox">
     <h3>بارگذاری امن مدارک پزشکی</h3>
     <p className="subtle">PDF، JPG یا PNG تا ۸ مگابایت؛ فقط پس از رضایت «مدارک پزشکی».</p>
     <div className="uploadRow"><input type="file" aria-label="انتخاب فایل مدرک" accept=".pdf,.jpg,.jpeg,.png" onChange={e=>setDocumentFile(e.target.files?.[0]||null)}/><button className="button" disabled={busy||!documentFile} onClick={()=>uploadDocument(c.case_id)}>بارگذاری امن</button></div>
     {documentStatus&&<p role="status">{documentStatus}</p>}
     <button className="button secondary" disabled={busy} type="button" onClick={()=>loadDocuments(c.case_id)}>نمایش مدارک من</button>
     {documentsByCase[c.case_id]&&(documentsByCase[c.case_id].length===0?<p className="subtle">مدرکی در دسترس نیست.</p>:<ul className="docList">{documentsByCase[c.case_id].map(d=><li key={d.id}>
      <span dir="auto">{d.filename}</span><span className={'badge '+tone(d.status)}>{fa(d.status)}</span><button className="button secondary" disabled={busy} type="button" onClick={()=>downloadDocument(c.case_id,d.id)}>دریافت</button>
     </li>)}</ul>)}
    </div>
    {c.travel&&<TripPlan t={c.travel}/>}
    <div className="portalGrid">
     <div><h3>خدمات سفر و درمان</h3>{c.services.length===0?<p className="subtle">خدمت فعالی ثبت نشده است.</p>:c.services.map((s,i)=><p key={i}>{fa(s.service)} — <span className={'badge '+tone(s.status)}>{fa(s.status)}</span></p>)}</div>
     <div><h3>نوبت‌های تأییدشده</h3>{c.confirmed_appointments.length===0?<p className="subtle">نوبت تأییدشده‌ای ندارید.</p>:c.confirmed_appointments.map((a,i)=><p key={i}>{fmtDate(a.at)}</p>)}</div>
     <div><h3>برآورد هزینه تأییدشده</h3>{c.approved_quotes.length===0?<p className="subtle">برآورد تأییدشده‌ای ثبت نشده است.</p>:c.approved_quotes.map(q=><p key={q.id}>{money(q.amount_minor,q.currency)}</p>)}</div>
    </div>
   </section>)}
   {intake&&<section className="panel portalPanel portalIntake"><h2>{copy.intake} · {fa(intake.status)}</h2><p className="subtle">مرحله {(intake.stage+1).toLocaleString('fa-IR')} از ۵</p>{intake.next_prompt?<form onSubmit={answerIntake}><p dir="auto" className="intakePrompt">{intake.next_prompt}</p><textarea dir="auto" required maxLength={3000} value={intakeAnswer} onChange={e=>setIntakeAnswer(e.target.value)} aria-label="پاسخ شما"/><p><button className="button" disabled={busy}>{copy.answer}</button></p></form>:<p>پاسخ‌های شما برای بررسی کارشناس ثبت شد. در شرایط اورژانسی از این سامانه استفاده نکنید.</p>}</section>}
   <section className="panel portalPanel"><div className="portalCaseHead"><h2>{copy.chat}</h2><label className="inlineLabel">{copy.language} <select value={chatLocale} onChange={e=>setChatLocale(e.target.value)}>{Object.keys(LANGUAGE_LABELS).map(code=><option key={code} value={code}>{LANGUAGE_LABELS[code]}</option>)}</select></label></div><p className="subtle">{copy.notice}</p>
    <div className="chatStream">{messages.length===0?<p className="subtle">هنوز پیامی ارسال نشده است.</p>:messages.map((m,i)=><div key={i} className={m.sender==='patient'?'chatBubble mine':'chatBubble'}><small>{SENDER[m.sender]||fa(m.sender)}</small><div dir="auto">{m.body}</div></div>)}</div>
    <form onSubmit={send} className="messageComposer"><input dir={chatLocale==='en'?'ltr':'rtl'} lang={chatLocale} required maxLength={4000} value={input} onChange={e=>setInput(e.target.value)} placeholder={copy.placeholder} aria-label={copy.placeholder}/><button className="button" disabled={busy}>{busy?'…':copy.send}</button></form>
   </section>
  </>}
 </main>;
}
