'use client';
import Shell from '@/components/Shell';
import {Row,request} from '@/lib/api';
import {useEffect,useState} from 'react';

type PublishedTranslation={title:string;locale:string;slug:string;summary:string};
type Manifest={
 tenant_slug:string;locales:string[];pages:{slug:string;translations:Record<string,PublishedTranslation>}[];
 required_slugs:string[];missing_translations:Record<string,string[]>;
 all_languages_complete:boolean;search_indexing_allowed:boolean;
 indexing_opt_in:boolean;legal_review_self_attested:boolean;
};
type CmsDetail={id:string;slug:string;locale:string;status:string;title:string;body:string};
const localeNames:Record<string,string>={fa:'فارسی',ar:'العربية',en:'English',ps:'پښتو',prs:'دری'};

export default function Cms(){
 const [pages,setPages]=useState<Row[]>([]);
 const [title,setTitle]=useState(''),[slug,setSlug]=useState(''),[body,setBody]=useState('');
 const [locale,setLocale]=useState('fa'),[tenant,setTenant]=useState('medtour-local');
 const [manifest,setManifest]=useState<Manifest|null>(null);
 const [editing,setEditing]=useState<CmsDetail|null>(null);
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);

 async function refresh(currentTenant?:string){
  const rows=await request<Row[]>('/cms/pages');
  setPages(rows);
  const s=currentTenant||tenant;
  if(!/^[a-z0-9][a-z0-9-]{0,62}$/.test(s)){setManifest(null);return;}
  try{
   const {API_BASE}=await import('@/lib/api');
   const result=await fetch(API_BASE+'/api/v1/public/'+encodeURIComponent(s)+'/site-manifest',{cache:'no-store'});
   setManifest(result.ok?await result.json() as Manifest:null);
  }catch{setManifest(null);}
 }
 useEffect(()=>{
  const slug=sessionStorage.getItem('medtour_tenant_slug')||'medtour-local';
  setTenant(slug);void refresh(slug).catch(e=>setError((e as Error).message));
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 async function submit(path:string,options:RequestInit){
  setBusy(true);setError('');setNotice('');
  try{
   await request(path,options);setNotice('تغییرات داخلی ثبت شد. بازبینی تخصصی ترجمه/حقوق/محتوای پزشکی همچنان بر عهده مدیر است.');
   await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function create(e:React.FormEvent){e.preventDefault();await submit('/cms/pages',{method:'POST',body:JSON.stringify({title,slug,body,locale})});}
 async function bootstrap(){
  await submit('/cms/public-site/bootstrap',{method:'POST',body:'{}'});
 }
 async function publish(id:string){
  if(!window.confirm('آیا همه ادعاهای پزشکی، ترجمه و متن حقوقی توسط افراد مسئول بررسی شده‌اند؟ انتشار صرفاً تأیید اداری است.'))return;
  await submit('/cms/pages/'+id+'/publish',{method:'PATCH'});
 }
 async function unpublish(id:string){await submit('/cms/public-site/pages/'+id+'/unpublish',{method:'PATCH'});}
 async function editDraft(id:string){
  try{
   const x=await request<CmsDetail>('/cms/public-site/drafts/'+id);
   if(x.status!=='draft')throw new Error('ابتدا صفحه را از انتشار خارج کنید.');
   setEditing(x);
  }catch(e){setError((e as Error).message);}
 }
 async function saveEdit(e:React.FormEvent){e.preventDefault();if(!editing)return;
  await submit('/cms/public-site/drafts/'+editing.id,{method:'PATCH',
   body:JSON.stringify({title:editing.title,body:editing.body})});
  setEditing(null);
 }
 return <Shell title="وب‌سایت عمومی چندزبانه">
  <div className="infoBanner">محتوای پیش‌نویس هرگز عمومی نیست. فعال‌سازی سئو به انتشار تمام صفحات اصلی به پنج زبان، بررسی حقوقی اعلام‌شده توسط سازمان و تنظیم صریح نیاز دارد. این تأیید به معنی بررسی مستقل قانون یا پزشک نیست.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  <section className="panel" style={{padding:20,marginBottom:22}}>
   <h2>۱. پیش‌نویس‌های سایت و وضعیت ترجمه</h2>
   <div style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'end'}}>
    <label>شناسه سازمان<input value={tenant} dir="ltr" onChange={e=>setTenant(e.target.value)}/></label>
    <button className="button" disabled={busy} onClick={()=>void refresh().catch(e=>setError((e as Error).message))}>بررسی انتشار</button>
    <button className="button" disabled={busy} onClick={()=>void bootstrap()}>افزودن ۴۰ پیش‌نویس پنج‌زبانه (بدون انتشار)</button>
    <a href={'/public/'+encodeURIComponent(tenant)+'/fa'} target="_blank" rel="noopener noreferrer">پیش‌نمایش فارسی وب‌سایت ↗</a>
   </div>
   {manifest&&<div style={{marginTop:20}}>
    <p>پوشش کامل پنج‌زبانه: <strong>{manifest.all_languages_complete?'بله':'خیر'}</strong> · اجازه نمایه‌سازی: <strong>{manifest.search_indexing_allowed?'فعال':'غیرفعال'}</strong></p>
    <div className="tableScroll"><table>
     <thead><tr><th>صفحه</th><th>فارسی</th><th>عربی</th><th>انگلیسی</th><th>پشتو</th><th>دری</th></tr></thead>
     <tbody>{manifest.required_slugs.map(s=><tr key={s}>
      <td dir="ltr">{s}</td>{['fa','ar','en','ps','prs'].map(l=><td key={l}>
       {manifest.missing_translations[l]?.includes(s)?'نیازمند بررسی/انتشار':'منتشر شده'}
      </td>)}
     </tr>)}</tbody>
    </table></div>
    <p>پس از بازبینی مستقل حقوقی و ترجمه، در تنظیمات سازمان کلید <code>public_portal</code> را با ساختار <code>{'{"search_indexing_enabled":true,"legal_content_reviewed":true}'}</code> تنظیم کنید. بدون URL عمومی HTTPS، صفحات همچنان noindex می‌مانند.</p>
   </div>}
  </section>
  <section className="panel" style={{padding:20,marginBottom:22}}>
   <h2>۲. افزودن پیش‌نویس</h2>
   <form className="formGrid" onSubmit={create}>
    <label>شناسه مسیر انگلیسی<input required dir="ltr" pattern="[a-z0-9]+(-[a-z0-9]+)*" value={slug} onChange={e=>setSlug(e.target.value)}/></label>
    <label>زبان<select value={locale} onChange={e=>setLocale(e.target.value)}>{['fa','ar','en','ps','prs'].map(x=><option key={x} value={x}>{localeNames[x]||x}</option>)}</select></label>
    <label>عنوان<input required value={title} maxLength={250} onChange={e=>setTitle(e.target.value)}/></label>
    <label>متن امن بدون HTML<textarea required rows={6} value={body} onChange={e=>setBody(e.target.value)}/></label>
    <button className="button" disabled={busy}>ذخیره پیش‌نویس</button>
   </form>
  </section>
  {editing&&<section className="panel" style={{padding:20,marginBottom:22}}>
   <h2>۳. ویرایش پیش‌نویس · {editing.slug} ({editing.locale})</h2>
   <form className="formGrid" onSubmit={saveEdit}>
    <label>عنوان<input required value={editing.title} onChange={e=>setEditing({...editing,title:e.target.value})}/></label>
    <label>متن<textarea required rows={9} value={editing.body} onChange={e=>setEditing({...editing,body:e.target.value})}/></label>
    <div style={{display:'flex',gap:12}}>
     <button className="button" disabled={busy}>ذخیره اصلاحات</button>
     <button className="button secondary" type="button" onClick={()=>setEditing(null)}>انصراف</button>
    </div>
   </form>
  </section>}
  <section className="panel" style={{padding:20}}>
   <h2>۴. لیست و انتشار محتوای بررسی‌شده</h2>
   <div className="tableScroll"><table>
    <thead><tr><th>عنوان</th><th>مسیر</th><th>زبان</th><th>وضعیت</th><th>عملیات</th></tr></thead>
    <tbody>{pages.map(x=><tr key={String(x.id)}>
     <td>{String(x.title)}</td><td dir="ltr">{String(x.slug)}</td><td>{String(x.locale)}</td>
     <td>{x.status==='published'?'منتشر شده':'پیش‌نویس'}</td>
     <td>{x.status==='published'?
      <button className="button secondary" disabled={busy} onClick={()=>void unpublish(String(x.id))}>لغو انتشار</button>:
      <div style={{display:'flex',gap:8}}>
       <button className="button secondary" disabled={busy} onClick={()=>void editDraft(String(x.id))}>ویرایش</button>
       <button className="button" disabled={busy} onClick={()=>void publish(String(x.id))}>انتشار با تأیید مدیر</button>
      </div>}
     </td>
    </tr>)}</tbody>
   </table></div>
  </section>
 </Shell>;
}
