'use client';
import Shell from '@/components/Shell';
import {API_BASE,getSession,request} from '@/lib/api';
import {useCallback,useEffect,useRef,useState} from 'react';

type Draft={id:string;locale:string;kind:string;status:string;duration_ms:number;
 transcript_sha256:string|null;source_format:string};
type Transcript=Draft&{draft_text:string|null;deduplicated:boolean};
type Ready={supported_locales:string[];stt_enabled_locales:string[];
 tts_enabled_locales:string[];demo_only:boolean};
const langs=[['fa','فارسی'],['ar','العربية'],['en','English'],['ps','پښتو'],['prs','دری']];
const intents=['greeting','appointment','quote','documents','visa','human','general'];

export default function VoiceMedia(){
 const [ready,setReady]=useState<Ready|null>(null);
 const [drafts,setDrafts]=useState<Draft[]>([]);
 const [role,setRole]=useState('');
 const [locale,setLocale]=useState('fa');
 const [file,setFile]=useState<File|null>(null);
 const [transcript,setTranscript]=useState('');
 const [created,setCreated]=useState('');
 const [reviewId,setReviewId]=useState('');
 const [reviewText,setReviewText]=useState('');
 const [reviewRef,setReviewRef]=useState('');
 const [intent,setIntent]=useState('greeting');
 const [playing,setPlaying]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const playerUrl=useRef<string>('');
 const refresh=useCallback(async()=>{
  const [status,items,me]=await Promise.all([
   request<Ready>('/voice/readiness'),
   request<{items:Draft[]}>('/voice/drafts'),
   request<{role:string}>('/auth/me')]);
  setReady(status);setDrafts(items.items);setRole(me.role);
 },[]);
 useEffect(()=>{void refresh().catch(e=>setError((e as Error).message));
  return()=>{if(playerUrl.current)URL.revokeObjectURL(playerUrl.current);};
 },[refresh]);

 async function transcribe(e:React.FormEvent){
  e.preventDefault();
  if(!file)return;
  setBusy(true);setError('');setNotice('');setTranscript('');
  try{
   const form=new FormData();
   form.append('file',file);
   form.append('locale',locale);
   form.append('request_key','VOICE-'+crypto.randomUUID());
   form.append('synthetic_sample_only','true');
   const resp=await fetch(API_BASE+'/api/v1/voice/transcribe',{
    method:'POST',headers:{Authorization:'Bearer '+getSession()},body:form,cache:'no-store'});
   const data=await resp.json() as Transcript&{detail?:string};
   if(!resp.ok)throw Error(data.detail||'Transcription failed');
   setTranscript(data.draft_text||'');
   setCreated(data.id);
   setNotice('پیش‌نویس فقط در همین تب نمایش داده شد. متن و صوت خام ذخیره نشدند؛ پیش از هر استفاده بررسی انسانی لازم است.');
   await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }

 async function generate(){
  setBusy(true);setError('');setNotice('');
  try{
   const res=await fetch(API_BASE+'/api/v1/voice/speak',{
    method:'POST',cache:'no-store',
    headers:{Authorization:'Bearer '+getSession(),'Content-Type':'application/json'},
    body:JSON.stringify({locale,intent,synthetic_sample_only:true})});
   if(!res.ok){
    const x=await res.json().catch(()=>({detail:'تولید صوت ناموفق بود.'}));
    throw Error(String(x.detail||'Speech synthesis failed'));
   }
   if(!res.headers.get('content-type')?.includes('audio/wav'))
    throw Error('فرمت خروجی مجاز نیست.');
   const blob=await res.blob();
   if(blob.size>1_100_000)throw Error('حجم صوت خروجی نامعتبر است.');
   if(playerUrl.current)URL.revokeObjectURL(playerUrl.current);
   playerUrl.current=URL.createObjectURL(blob);
   setPlaying(playerUrl.current);
   setNotice('نمونه صوت فقط در مرورگر برای شنیدن دستی ساخته شد؛ هیچ پیامی به بیمار ارسال نشده است.');
   await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }

 async function review(decision:'approve_internal'|'reject'){
  if(!reviewId)return;
  setBusy(true);setError('');setNotice('');
  try{
   await request('/voice/drafts/'+reviewId+'/review',{
    method:'POST',body:JSON.stringify({
     decision,transcript_text:reviewText,evidence_reference:reviewRef})});
   setReviewText('');
   setNotice('نظر انسانی ثبت شد. هیچ فایل صوتی یا پاسخ به پیام‌رسان ارسال نشده است.');
   await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Shell title="پیام صوتی چندزبانه — STT / TTS">
  <div className="infoBanner">
   <strong>فقط محیط آزمایش با فایل ساختگی.</strong> ارسال فایل پزشکی یا صدای واقعی بیمار مجاز نیست. این صفحه به واتساپ یا تلگرام متصل نیست؛ دریافت خودکار فایل صوتی و ارسال خودکار پاسخ غیرفعال‌اند. صوت خام و متن بازشناسی‌شده در پایگاه‌داده ذخیره نمی‌شوند. پشتو و دری بدون ارزیابی مستقل کیفیت گفتار قابل عرضه تجاری نیستند.
  </div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>۱. وضعیت پردازش و زبان‌ها</h2>
   <p>STT فعال و تأییدشده در پیکربندی: {ready?.stt_enabled_locales.join('، ')||'هیچ‌کدام'}</p>
   <p>TTS فعال و تأییدشده در پیکربندی: {ready?.tts_enabled_locales.join('، ')||'هیچ‌کدام'}</p>
   <p>فرمت ورود: WAV تک‌کاناله PCM16 یا OGG/Opus · حداکثر ۱ مگابایت · حداکثر ۳۰ ثانیه</p>
  </section>
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>۲. تبدیل صدای آزمایشی به متن (STT)</h2>
   <form onSubmit={transcribe} className="formGrid">
    <label>زبان نمونه<select value={locale} onChange={e=>setLocale(e.target.value)}>
     {langs.map(([value,label])=><option value={value} key={value}>{label}</option>)}
    </select></label>
    <label>فایل ساختگی محلی<input required type="file" accept=".wav,.ogg,audio/wav,audio/ogg"
     onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
    <div className="formActions">
     <button className="button" disabled={busy||!file||!ready?.stt_enabled_locales.includes(locale)}>
      تبدیل به پیش‌نویس غیرقطعی
     </button>
    </div>
   </form>
   {created&&<p>شناسه پیش‌نویس: <code>{created}</code></p>}
   {transcript&&<div style={{padding:18,background:'var(--surface,#f3f7f8)',whiteSpace:'pre-wrap'}}
      dir={locale==='en'?'ltr':'rtl'}>
    <strong>متن موقت — نیازمند بازبینی انسانی</strong>
    <p>{transcript}</p>
   </div>}
  </section>
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>۳. تولید صوت نمونه از پیام‌های اداری ثابت (TTS)</h2>
   <label>پیام ثابت<select value={intent} onChange={e=>setIntent(e.target.value)}>
    {intents.map(value=><option key={value} value={value}>{value}</option>)}
   </select></label>
   <button className="button secondary" disabled={busy||!ready?.tts_enabled_locales.includes(locale)}
    onClick={()=>void generate()}>تولید و شنیدن نمونه صوت</button>
   {playing&&<audio controls src={playing} aria-label="نمونه صوت آزمایشی" style={{display:'block',marginTop:15,maxWidth:'100%'}}/>}
  </section>
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>۴. بازبینی مستقل متن آزمایشی</h2>
   <p>بازبین مدیر باید متن دقیق را که از مسیر امن و موقت دریافت کرده وارد کند. هش با پیش‌نویس تطبیق داده می‌شود؛ نویسنده نمی‌تواند متن خودش را تأیید کند.</p>
   <div className="formGrid">
    <label>شناسه پیش‌نویس<select value={reviewId} onChange={e=>setReviewId(e.target.value)}>
     <option value="">انتخاب کنید</option>
     {drafts.filter(x=>x.kind==='stt'&&x.status==='pending_human_review').map(x=>
      <option key={x.id} value={x.id}>{x.id.slice(0,8)} · {x.locale}</option>)}
    </select></label>
    <label>مرجع غیرحساس بررسی<input value={reviewRef} maxLength={100}
     onChange={e=>setReviewRef(e.target.value)}/></label>
    <label style={{gridColumn:'1/-1'}}>متن تأییدشده دقیق<textarea rows={4} value={reviewText}
     onChange={e=>setReviewText(e.target.value)}/></label>
   </div>
   {role==='admin'&&<div style={{display:'flex',flexWrap:'wrap',gap:12,marginTop:12}}>
    <button className="button" disabled={busy||!reviewId||reviewRef.length<6||!reviewText}
     onClick={()=>void review('approve_internal')}>تأیید صرفاً داخلی</button>
    <button className="button secondary" disabled={busy||!reviewId||reviewRef.length<6||!reviewText}
     onClick={()=>void review('reject')}>رد متن</button>
   </div>}
  </section>
 </Shell>;
}
