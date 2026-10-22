'use client';
import Shell from '@/components/Shell';
import {request,Row} from '@/lib/api';
import {useEffect,useState} from 'react';

const languages=[['fa','فارسی'],['ar','العربية'],['en','English'],['ps','پښتو'],['prs','دری']];
const templates=['case_update_available','appointment_update_available','please_check_secure_portal'];
export default function Messaging(){
 const [conversationId,setConversationId]=useState(''),[locale,setLocale]=useState('ar');
 const [template,setTemplate]=useState(templates[0]);const [items,setItems]=useState<Row[]>([]);
 const [source,setSource]=useState(''),[translation,setTranslation]=useState(''),[translationId,setTranslationId]=useState('');
 const [sourceLang,setSourceLang]=useState('fa'),[targetLang,setTargetLang]=useState('ar');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [telegramStatus,setTelegramStatus]=useState('در حال بررسی');
 const [channelOverview,setChannelOverview]=useState<Record<string,{configured:boolean,live_verified:boolean,capability:string}>>({});
 const [handoffCases,setHandoffCases]=useState<{id:string,status:string}[]>([]);
 const [handoffCaseId,setHandoffCaseId]=useState('');
 const [handoffBusy,setHandoffBusy]=useState(false);
 async function refresh(){try{setItems(await request<Row[]>('/communications/outbound'))}catch(e){setError((e as Error).message)}}
 useEffect(()=>{
    void request<{channels:Record<string,{configured:boolean,live_verified:boolean,capability:string}>}>('/channels/readiness')
      .then(data=>setChannelOverview(data.channels)).catch(()=>{});
    void request<{id:string,status:string}[]>('/cases')
      .then(rows=>{setHandoffCases(rows);setHandoffCaseId(rows[0]?.id||'');}).catch(()=>{});
    void refresh();
    void request<{telegram?:{status:string,live_connected:boolean}}>('/integrations/status')
      .then(data=>setTelegramStatus(data.telegram?.status==='generic_onboarding_configured'?
        'پیکربندی اولیه انجام شده؛ ارسال و دریافت زنده هنوز تأیید نشده است':
        'غیرفعال یا نیازمند تنظیمات رسمی ربات'))
      .catch(()=>setTelegramStatus('وضعیت سرویس در دسترس نیست'));
 },[]);
 async function queue(e:React.FormEvent){e.preventDefault();setError('');setNotice('');setBusy(true);
  try{const id=crypto.randomUUID().replaceAll('-','');const r=await request<{id:string,status:string}>('/communications/outbound',{method:'POST',body:JSON.stringify({conversation_id:conversationId,locale,template_name:template,idempotency_key:id})});setNotice(`درخواست ${String(r.id).slice(0,8)} در انتظار تأیید مدیر است؛ پیامی ارسال نشده.`);await refresh()}
  catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function approve(id:string){setError('');try{await request(`/communications/outbound/${id}/approve`,{method:'POST'});setNotice('قالب تأیید شد؛ ارسال فقط توسط پردازشگر رسمی و پس از فعال‌سازی مجوزها انجام می‌شود.');await refresh()}catch(e){setError((e as Error).message)}}
 async function draft(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setNotice('');try{const r=await request<{id:string,draft_text:string}>('/communications/translation-drafts',{method:'POST',body:JSON.stringify({conversation_id:conversationId,source_language:sourceLang,target_language:targetLang,source_text:source})});setTranslation(r.draft_text);setTranslationId(r.id);setNotice('ترجمه پیش‌نویس است و باید قبل از انتشار توسط اپراتور بررسی شود.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function publish(){setBusy(true);setError('');try{await request(`/communications/translation-drafts/${translationId}/review`,{method:'POST',body:JSON.stringify({approved_text:translation,action:'approve'})});setTranslationId('');setNotice('ترجمه تأیید و فقط در گفت‌وگوی امن وب ثبت شد.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function preparePortalHandoff(){
  if(!handoffCaseId)return;
  setHandoffBusy(true);setError('');setNotice('');
  try{
   const result=await request<{status:string,deduplicated:boolean,sent:boolean}>('/channels/cases/'+encodeURIComponent(handoffCaseId)+'/secure-portal-handoff',{method:'POST'});
   setNotice(result.deduplicated?'درخواست قبلی دعوت امن هنوز باز است؛ پیام جدیدی ارسال نشد.':'وظیفه دعوت امن برای اپراتور ثبت شد. پیام یا لینک به بیمار ارسال نشده است.');
  }catch(e){setError((e as Error).message)}
  finally{setHandoffBusy(false)}
 }
 return <Shell title="ارتباطات و ترجمه"><div className="infoBanner">پیام واتساپ صرفاً با قالب عمومی تأییدشده و رضایت ارتباطی ارسال می‌شود. اتصال رسمی پیش‌فرض غیرفعال است. ترجمه هوش مصنوعی مستقل از ارسال واتساپ و نیازمند رضایت و تأیید انسانی است.</div>{error&&<p className="errorBox" role="alert">{error}</p>}{notice&&<p className="infoBanner">{notice}</p>}
 <section className="panel" aria-label="مسیر واتس‌اپ و جایگزین امن">
 <div className="panelHeader"><h2>مسیر ارتباطی اصلی و جایگزین</h2></div>
 <div style={{padding:18}}>
  <p>کانال اصلی: <strong>WhatsApp</strong>. کانال جایگزین برای پرونده بیمار: <strong>دعوت انسانی به پرتال امن</strong>. تلگرام فقط راهنمای عمومی است و برای شناسایی بیمار به کار نمی‌رود.</p>
  <div style={{display:'flex',flexWrap:'wrap',gap:12,marginBottom:14}}>
   {Object.entries(channelOverview).map(([key,state])=><span className="badge" key={key}>
    {key}: {state.configured?'تنظیم‌شده (نه تأیید زنده)':'غیرفعال'} · {state.live_verified?'تأیید زنده':'بدون تأیید زنده'}
   </span>)}
  </div>
  <div className="formGrid">
   <label>پرونده برای ارجاع انسانی به پرتال امن
    <select value={handoffCaseId} onChange={e=>setHandoffCaseId(e.target.value)}>
     <option value="">انتخاب پرونده</option>
     {handoffCases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} — {c.status}</option>)}
    </select>
   </label>
   <div className="formActions">
    <button className="button secondary" type="button" disabled={!handoffCaseId||handoffBusy} onClick={preparePortalHandoff}>
     {handoffBusy?'در حال ثبت...':'ایجاد وظیفه دعوت امن'}
    </button>
   </div>
  </div>
  <p>این اقدام تنها یک وظیفه داخلی ایجاد می‌کند؛ اپراتور باید رضایت فعلی و هویت بیمار را بررسی کند. هیچ پیام خودکار یا لینک دسترسی ایجاد نمی‌شود.</p>
 </div>
 </section>
 <section className="panel" aria-label="کانال تلگرام"><div className="panelHeader"><h2>تلگرام — شروع گفت‌وگو با ربات</h2></div>
 <div style={{padding:18}}>
 <p>وضعیت: <strong>{telegramStatus}</strong></p>
 <p>این کانال فعلاً فقط پنج زبان و اطلاع‌رسانی عمومی را پشتیبانی می‌کند. برای دریافت اسناد و اطلاعات پزشکی از پرتال امن با رضایت بیمار استفاده کنید؛ اطلاعات حساس را در ربات ارسال نکنید.</p>
 <p>برای ساخت ربات از <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer">BotFather رسمی تلگرام</a> استفاده کنید. Token و Webhook Secret فقط در تنظیمات سرور قرار می‌گیرند، نه در این پنل.</p>
 </div></section>
 <div className="dashboardLower"><section className="panel"><div className="panelHeader"><h2>درخواست پیام واتساپ</h2></div><form className="formGrid" onSubmit={queue}>
 <label>شناسه مکالمه واتساپ<input required value={conversationId} onChange={e=>setConversationId(e.target.value)}/></label>
 <label>زبان قالب<select value={locale} onChange={e=>setLocale(e.target.value)}>{languages.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label>قالب غیرپزشکی<select value={template} onChange={e=>setTemplate(e.target.value)}>{templates.map(s=><option key={s} value={s}>{s}</option>)}</select></label>
 <div className="formActions"><button className="button" disabled={busy}>ثبت درخواست بدون ارسال</button></div></form></section>
 <section className="panel"><div className="panelHeader"><h2>ترجمه با بازبینی انسانی</h2></div><form className="formGrid" onSubmit={draft}>
 <label>زبان مبدأ<select value={sourceLang} onChange={e=>setSourceLang(e.target.value)}>{languages.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label>زبان مقصد<select value={targetLang} onChange={e=>setTargetLang(e.target.value)}>{languages.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label style={{gridColumn:'1/-1'}}>متن اصلی (فقط با رضایت بیمار)<textarea required value={source} onChange={e=>setSource(e.target.value)}/></label>
 <div className="formActions"><button className="button secondary" disabled={busy||!conversationId}>ایجاد پیش‌نویس AI</button></div></form>
 {translationId&&<div style={{padding:20}}><label>متن بازبینی‌شده<textarea style={{width:'100%'}} value={translation} onChange={e=>setTranslation(e.target.value)}/></label><button className="button" disabled={busy||!translation} onClick={publish}>تأیید برای وب‌چت</button></div>}</section></div>
 <section className="panel"><div className="panelHeader"><h2>پیام‌های خروجی در صف</h2><button className="button secondary" onClick={refresh}>بروزرسانی</button></div><div className="tableScroll"><table><thead><tr><th>شناسه</th><th>قالب</th><th>زبان</th><th>وضعیت</th><th>اقدام</th></tr></thead><tbody>{items.map(x=><tr key={String(x.id)}><td>{String(x.id).slice(0,8)}</td><td dir="ltr">{String(x.template_name)}</td><td>{String(x.locale)}</td><td>{String(x.status)}</td><td>{x.status==='pending_approval'&&<button className="button secondary" onClick={()=>approve(String(x.id))}>تأیید مدیر</button>}</td></tr>)}</tbody></table></div></section></Shell>}
