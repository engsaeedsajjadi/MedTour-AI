'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';

type Stage='translation'|'medical'|'legal';
type ReviewState='pending'|'approved'|'rejected';
type PageState={
 id:string;slug:string;locale:string;status:string;
 published_version_no:number|null;latest_version:number;latest_version_id:string|null;
 latest_state:string;latest_content_hash:string|null;
 review_stages:Record<Stage,ReviewState>;
};
type Version={id:string;page_id:string;version_no:number;title:string;body:string;
 content_hash:string;reason:string;author_id:string;status:string;created_at:string};
type Event={id:string;version_id:string|null;action:string;actor_id:string;
 reference:string;created_at:string};
const root='/cms/workflow';
const labels:Record<string,string>={
 draft:'پیش‌نویس',in_review:'در بررسی تخصصی',ready:'آماده انتشار',
 rejected:'ردشده',published:'منتشرشده',superseded:'جایگزین‌شده',
 withdrawn:'لغوشده',translation:'ترجمه',medical:'پزشکی',legal:'حقوقی',
 pending:'در انتظار',approved:'تأیید داخلی',unversioned:'بدون نسخه'
};
const localeNames:Record<string,string>={fa:'فارسی',ar:'عربی',en:'انگلیسی',ps:'پشتو',prs:'دری'};
const stages:Stage[]=['translation','medical','legal'];
export default function CmsWorkflow(){
 const [role,setRole]=useState('');
 const [pages,setPages]=useState<PageState[]>([]);
 const [selected,setSelected]=useState('');
 const [versions,setVersions]=useState<Version[]>([]);
 const [events,setEvents]=useState<Event[]>([]);
 const [title,setTitle]=useState(''),[body,setBody]=useState('');
 const [reason,setReason]=useState('Update reviewed informational content');
 const [reviewEvidence,setReviewEvidence]=useState('');
 const [reviewDecision,setReviewDecision]=useState<'approved'|'rejected'>('approved');
 const [restoreReason,setRestoreReason]=useState('Restored previous snapshot for fresh independent review');
 const [reviewerEmail,setReviewerEmail]=useState('');
 const [reviewerPassword,setReviewerPassword]=useState('');
 const [reviewerRole,setReviewerRole]=useState('cms_translator');
 const [compare,setCompare]=useState(0);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const current=pages.find(x=>x.id===selected);
 const latest=versions[0];
 const stage=stages.find(x=>role==='cms_'+(x==='translation'?'translator':x+'_reviewer'));
 const editing=role==='admin'||role==='cms_editor';

 async function reload(requested?:string){
  const data=await request<{items:PageState[]}>(root+'/pages');
  setPages(data.items);
  const id=requested||selected||data.items[0]?.id||'';
  setSelected(id);
  if(id)await loadPage(id);
 }
 async function loadPage(id:string){
  if(!id){setVersions([]);setEvents([]);return;}
  const [v,h]=await Promise.all([
   request<{items:Version[]}>(root+'/pages/'+id+'/versions'),
   request<{items:Event[]}>(root+'/pages/'+id+'/history')
  ]);
  setVersions(v.items);setEvents(h.items);setCompare(v.items.length>1?1:0);
  setTitle(v.items[0]?.title||'');setBody(v.items[0]?.body||'');
 }
 useEffect(()=>{(async()=>{
  const me=await request<{role:string}>('/auth/me');setRole(me.role);
  const requested=new URLSearchParams(window.location.search).get('page')||undefined;
  await reload(requested);
 })().catch(e=>setError((e as Error).message));
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);

 async function action(path:string,payload?:object){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,{method:'POST',body:payload===undefined?undefined:JSON.stringify(payload)});
   setNotice('ثبت شد. مدارک و صلاحیت متخصصان خارجی هنوز مستقلاً تأیید نشده‌اند؛ تأییدها صرفاً گردش‌کار داخلی هستند.');
   await reload(selected);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 const versionPath=selected?root+'/pages/'+encodeURIComponent(selected):'';
 async function addVersion(){
  if(!latest)return;
  await action(versionPath+'/versions',{title,body,
   expected_version:latest.version_no,reason});
 }
 async function review(){
  if(!stage)return;
  await action(versionPath+'/reviews/'+stage,{decision:reviewDecision,
   evidence_reference:reviewEvidence});
 }
 async function restoreVersion(id:string){
  if(!latest)return;
  await action(versionPath+'/versions/'+id+'/restore',{
   expected_version:latest.version_no,reason:restoreReason});
 }
 const status=(x:string)=>labels[x]||x;
 return <Shell title="نسخه‌بندی و تأیید سازمانی CMS">
  <div className="infoBanner">
   بخش ۲۳: هر تغییر یک نسخه مستقل تولید می‌کند. انتشار فقط پس از تأیید سه شخص متفاوت با نقش‌های ترجمه، بازبین پزشکی و بازبین حقوقی مجاز است. صلاحیت حرفه‌ای آن‌ها هنوز توسط سامانه یا مرجع خارجی تأیید نشده و این نسخه برای اطلاعات واقعی بیمار طراحی نشده است.
  </div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20,marginBlock:16}}>
   <h2>۱. صف صفحات و وضعیت تأیید</h2>
   <label>صفحه و زبان
    <select value={selected} onChange={e=>{setSelected(e.target.value);void loadPage(e.target.value).catch(x=>setError((x as Error).message));}}>
     <option value="">انتخاب کنید</option>
     {pages.map(p=><option key={p.id} value={p.id}>{p.slug} · {localeNames[p.locale]||p.locale} · {status(p.latest_state)}</option>)}
    </select>
   </label>
   {current&&<>
    <p>آخرین نسخه: {current.latest_version} · وضعیت نسخه: <strong>{status(current.latest_state)}</strong> · نسخه عمومی: {current.published_version_no||'ندارد'}</p>
    <div style={{display:'flex',gap:16,flexWrap:'wrap'}}>
     {stages.map(x=><span key={x}>{status(x)}: <strong>{status(current.review_stages[x])}</strong></span>)}
    </div>
   </>}
  </section>
  {current&&<section className="panel" style={{padding:20,marginBlock:16}}>
   <h2>۲. نسخه‌های تغییرناپذیر و مقایسه</h2>
   <p>عنوان، متن، نویسنده، دلیل تغییر و اثر SHA-256 هر نسخه برای حسابرسی حفظ می‌شوند.</p>
   {latest&&<div style={{display:'grid',gap:10}}>
    <p>نسخه جدیدتر: <strong>v{latest.version_no}</strong> · اثر محتوا: <code style={{overflowWrap:'anywhere'}}>{latest.content_hash}</code></p>
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(270px,1fr))',gap:15}}>
     <div style={{border:'1px solid #dce5e9',padding:13,borderRadius:12}}>
      <strong>آخرین نسخه · v{latest.version_no}</strong>
      <p>{latest.title}</p>
      <div style={{whiteSpace:'pre-wrap',maxHeight:220,overflowY:'auto'}}>{latest.body}</div>
     </div>
     {versions.length>1&&<div style={{border:'1px solid #dce5e9',padding:13,borderRadius:12}}>
      <label>مقایسه با نسخه قبلی<select value={compare} onChange={e=>setCompare(Number(e.target.value))}>
       {versions.slice(1).map((v,i)=><option key={v.id} value={i+1}>v{v.version_no} · {status(v.status)}</option>)}
      </select></label>
      <p>{versions[compare]?.title}</p>
      <div style={{whiteSpace:'pre-wrap',maxHeight:220,overflowY:'auto'}}>{versions[compare]?.body}</div>
     </div>}
    </div>
   </div>}
   <div className="tableScroll"><table><thead><tr><th>نسخه</th><th>وضعیت</th><th>دلیل</th><th>نویسنده</th><th>عملیات</th></tr></thead>
    <tbody>{versions.map((v,i)=><tr key={v.id}><td>v{v.version_no}</td><td>{status(v.status)}</td><td>{v.reason}</td><td>{v.author_id.slice(0,8)}</td><td>
     {editing&&i!==0&&<button className="button secondary" disabled={busy||restoreReason.length<6} onClick={()=>void restoreVersion(v.id)}>ساخت نسخه تازه از این نسخه</button>}
    </td></tr>)}</tbody></table></div>
  </section>}
  {current&&editing&&<section className="panel" style={{padding:20,marginBlock:16}}>
   <h2>۳. ایجاد نسخه و ارسال برای بازبینی</h2>
   <div style={{display:'grid',gap:10,maxWidth:750}}>
    <label>عنوان<input value={title} onChange={e=>setTitle(e.target.value)} maxLength={250}/></label>
    <label>متن غیرحساس<textarea rows={8} value={body} onChange={e=>setBody(e.target.value)}/></label>
    <label>دلیل تغییر<input value={reason} maxLength={200} onChange={e=>setReason(e.target.value)}/></label>
    <button className="button" disabled={busy||!latest||title.length<2||!body.trim()||reason.length<6} onClick={()=>void addVersion()}>ساخت نسخه جدید · تأییدهای قبلی منتقل نمی‌شوند</button>
    {current.latest_state==='draft'&&<button className="button secondary" disabled={busy} onClick={()=>void action(versionPath+'/submit')}>ارسال آخرین نسخه برای سه بازبینی مستقل</button>}
   </div>
  </section>}
  {current&&stage&&<section className="panel" style={{padding:20,marginBlock:16}}>
   <h2>۴. بازبینی تخصصی {status(stage)}</h2>
   <p>فقط نسخه فعلیِ در حال بررسی. نویسنده نمی‌تواند متن خودش را تأیید کند.</p>
   <div style={{display:'grid',gap:12,maxWidth:650}}>
    <label>نتیجه<select value={reviewDecision} onChange={e=>setReviewDecision(e.target.value as 'approved'|'rejected')}>
     <option value="approved">تأیید داخلی</option><option value="rejected">رد و بازگشت برای نسخه جدید</option>
    </select></label>
    <label>مرجع بازبینی غیرحساس<input dir="ltr" placeholder="REVIEW-LOCAL-REFERENCE-123" value={reviewEvidence} onChange={e=>setReviewEvidence(e.target.value)}/></label>
    <button className="button" disabled={busy||current.latest_state!=='in_review'||reviewEvidence.length<6||current.review_stages[stage]!=='pending'} onClick={()=>void review()}>ثبت تصمیم نسخه فعلی</button>
   </div>
  </section>}
  {current&&role==='admin'&&<section className="panel" style={{padding:20,marginBlock:16}}>
   <h2>۵. تأیید انتشار و حساب بازبینان</h2>
   <button className="button" disabled={busy||current.latest_state!=='ready'} onClick={()=>void action(versionPath+'/publish')}>انتشار فقط پس از تأیید هر سه بازبین</button>
   <p>برای محیط واقعی، صلاحیت تخصصی و استقلال بازبینان باید خارج از برنامه تأیید و ثبت شود.</p>
   <div style={{display:'grid',gap:10,maxWidth:620}}>
    <label>نقش بازبین<select value={reviewerRole} onChange={e=>setReviewerRole(e.target.value)}>
     <option value="cms_editor">نویسنده و ویراستار</option>
     <option value="cms_translator">بازبین ترجمه</option>
     <option value="cms_medical_reviewer">بازبین پزشکی</option>
     <option value="cms_legal_reviewer">بازبین حقوقی</option>
    </select></label>
    <label>ایمیل حساب آزمایشی<input type="email" dir="ltr" value={reviewerEmail} onChange={e=>setReviewerEmail(e.target.value)}/></label>
    <label>گذرواژه اولیه امن<input type="password" minLength={16} value={reviewerPassword} onChange={e=>setReviewerPassword(e.target.value)}/></label>
    <button className="button secondary" disabled={busy||reviewerPassword.length<16||!reviewerEmail.includes('@')}
     onClick={()=>{void action(root+'/reviewers',{email:reviewerEmail,password:reviewerPassword,role:reviewerRole}).then(()=>setReviewerPassword(''));}}>ایجاد حساب نقش تخصصی (بدون تأیید صلاحیت)</button>
   </div>
  </section>}
  {current&&<section className="panel" style={{padding:20,marginBlock:16}}>
   <h2>۶. تاریخچه حسابرسی</h2>
   <div className="tableScroll"><table><thead><tr><th>زمان</th><th>عملیات</th><th>مرجع</th><th>بازیگر</th></tr></thead>
    <tbody>{events.map(e=><tr key={e.id}><td>{new Date(e.created_at).toLocaleString('fa-IR')}</td>
     <td>{e.action}</td><td dir="ltr">{e.reference}</td><td>{e.actor_id.slice(0,8)}</td></tr>)}</tbody></table></div>
  </section>}
 </Shell>;
}
