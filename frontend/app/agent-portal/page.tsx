'use client';
import {useEffect,useState} from 'react';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
type Profile={agent_id:string;agent_name:string;country:string;agreement_status:string;referral_code:string;clinical_data_access:boolean;commission_payments_enabled:boolean};
type Intent={id:string;request_key:string;channel:string;campaign_code:string;status:string;created_at:string;patient_information_shared:boolean};
const root='/agent-network/portal';
export default function AgentPortal(){
 const [profile,setProfile]=useState<Profile|null>(null),[items,setItems]=useState<Intent[]>([]);
 const [channel,setChannel]=useState('web'),[campaign,setCampaign]=useState('DEMO2026');
 const [error,setError]=useState(''),[info,setInfo]=useState(''),[busy,setBusy]=useState(false);
 async function reload(){
  const [p,r]=await Promise.all([
   request<Profile>(root+'/me'),request<{items:Intent[]}>(root+'/referrals')]);
  setProfile(p);setItems(r.items);
 }
 useEffect(()=>{void reload().catch(e=>setError((e as Error).message));},[]);
 async function submit(){
  setBusy(true);setError('');setInfo('');
  try{
   await request(root+'/referrals',{method:'POST',body:JSON.stringify({
    request_key:'REF-'+crypto.randomUUID(),channel,campaign_code:campaign
   })});setInfo('شناسه پیگیری غیرحساس ثبت شد. شناسایی و رضایت بیمار فقط توسط مدیر پیگیری می‌شود.');
   await reload();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <Shell title="پرتال اختصاصی نماینده">
  <div className="infoBanner">این پرتال آزمایشی تنها برای ثبت شناسه پیگیری ارجاع بدون اطلاعات بیمار است. نام، شماره تماس، تشخیص، مدارک، پرونده پزشکی یا درخواست مالی را وارد نکنید. هیچ پرداختی در این نسخه فعال نیست.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {info&&<div className="infoBanner" role="status">{info}</div>}
  {profile&&<section className="panel" style={{padding:20,marginTop:16}}>
   <h2>مشخصات نماینده</h2>
   <p>{profile.agent_name} · {profile.country}</p>
   <p>کد ارجاع: <code>{profile.referral_code}</code></p>
   <p>قرارداد: بررسی اداری انجام شده (نه تأیید مستقل حقوقی)</p>
   <p>دسترسی به اطلاعات بیمار: خیر · پرداخت کارمزد: غیرفعال</p>
  </section>}
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>ثبت ارجاع بدون اطلاعات شخصی</h2>
   <div style={{display:'grid',gap:10,maxWidth:530}}>
    <label>کانال<select value={channel} onChange={e=>setChannel(e.target.value)}>
     <option value="web">وب</option><option value="whatsapp">واتس‌اپ</option>
     <option value="telegram">تلگرام</option><option value="offline">آفلاین</option>
    </select></label>
    <label>کد کمپین غیرشخصی<input value={campaign} onChange={e=>setCampaign(e.target.value)} maxLength={60}/></label>
    <button disabled={busy||campaign.length<3} onClick={()=>void submit()}>ثبت کد پیگیری</button>
   </div>
  </section>
  <section className="panel" style={{padding:20,marginTop:16}}>
   <h2>پیگیری ارجاع‌های خودم</h2>
   {items.length===0?<p>هنوز شناسه‌ای ثبت نشده است.</p>:items.map(x=><div key={x.id} style={{padding:'12px 0',borderTop:'1px solid #d4dde7'}}>
    <strong>{x.request_key} · {x.status==='attributed'?'ارجاع منتسب شده':x.status==='blocked'?'ارجاع مسدود': 'منتظر بررسی داخلی'}</strong>
    <p>کانال: {x.channel} · کمپین: {x.campaign_code} · {new Date(x.created_at).toLocaleString('fa-IR')}</p>
    <small>هیچ اطلاعات هویتی یا درمانی ارائه نمی‌شود.</small>
   </div>)}
  </section>
 </Shell>;
}
