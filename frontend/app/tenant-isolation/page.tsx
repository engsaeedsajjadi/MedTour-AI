'use client';
import Shell from '@/components/Shell';
import {request} from '@/lib/api';
import {useEffect,useState} from 'react';

type Status={
 database:string;tenant_scoped_tables:number;composite_tenant_fks:number;
 rls_policy_tables:number;rls_force_tables:number;
 runtime_role_nonprivileged:boolean;authenticated_tenant_role:boolean;
 verified_end_to_end_routing:boolean;production_ready:boolean;reason:string;
};
type Check={key:string;label:string;passed:boolean;kind:string};
type Readiness={real_patient_data_mode:boolean;ready_for_real_patients:boolean;checks:Check[]};
export default function TenantIsolation(){
 const [state,setState]=useState<Status|null>(null);
 const [ready,setReady]=useState<Readiness|null>(null);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 async function refresh(){
  setLoading(true);setError('');
  try{const [s,r]=await Promise.all([request<Status>('/admin/tenant-isolation/status'),request<Readiness>('/compliance/readiness')]);setState(s);setReady(r);}
  catch(e){setError((e as Error).message);}finally{setLoading(false);}
 }
 useEffect(()=>{void refresh();},[]);
 const values=[
  ['جدول‌های تفکیک‌شده بر اساس سازمان',state?.tenant_scoped_tables??'-'],
  ['کلیدهای خارجی مرکب',state?.composite_tenant_fks??'-'],
  ['جدول‌های دارای سیاست امنیت سطری',state?.rls_policy_tables??'-'],
  ['جدول‌های دارای اجبار امنیت سطری در پایگاه داده',state?.rls_force_tables??'-']
 ];
 return <Shell title="ممیزی جداسازی سازمان‌ها">
  <div className="infoBanner">این صفحه وضعیت جداسازی داده سازمان‌ها در پایگاه داده و چک‌لیست آمادگی عملیاتی را نشان می‌دهد. موارد حقوقی فقط با ثبت شماره مرجع تصمیم‌های رسمی تکمیل می‌شوند.</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  <section className="panel" style={{padding:20,marginTop:18}}>
   <h2>وضعیت دیتابیس فعلی</h2>
   {loading?<p>در حال دریافت وضعیت…</p>:<>
    <p>نوع پایگاه‌داده: <strong>{state?.database||'نامشخص'}</strong></p>
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(190px,1fr))',gap:12}}>
     {values.map(([name,value])=><div key={String(name)} style={{padding:18,border:'1px solid #dce4e9',borderRadius:12}}>
      <strong style={{display:'block',fontSize:24}}>{value}</strong><span>{name}</span>
     </div>)}
    </div>
    <h3 style={{marginTop:20}}>کنترل‌های اجرا</h3>
    <div style={{display:'grid',gap:8}}>
     <p>نقش دیتابیس غیرممتاز: <strong>{state?.runtime_role_nonprivileged?'بله':'خیر / اثبات نشده'}</strong></p>
     <p>هویت سازمان مستقل از اتصال: <strong>{state?.authenticated_tenant_role?'تأیید شده':'هنوز متصل نشده'}</strong></p>
     <p>مسیریابی امن همه مسیرهای API: <strong>{state?.verified_end_to_end_routing?'تأیید شده':'ناقص'}</strong></p>
     <p>آمادگی برای استقرار نهایی: <strong>{state?.production_ready?'تأیید شده':'خیر'}</strong></p>
     <p>{state?.reason}</p>
    </div>
   </>}
   <button className="button" style={{marginTop:14}} disabled={loading} onClick={()=>void refresh()}>بررسی مجدد</button>
  </section>
  {ready&&<section className="panel" style={{padding:20}}>
   <div className="portalCaseHead"><h2>آمادگی عملیاتی برای پذیرش بیمار</h2><span className={'badge '+(ready.ready_for_real_patients?'':'danger')}>{ready.ready_for_real_patients?'آماده':'آماده نیست'}</span></div>
   <p>حالت عملیاتی بیمار: <strong>{ready.real_patient_data_mode?'فعال':'غیرفعال'}</strong> · سامانه تا تکمیل همه موارد زیر اجازه فعال شدن این حالت را نمی‌دهد.</p>
   {(['technical','legal','review'] as const).map(kind=><div key={kind}><h3>{kind==='technical'?'کنترل‌های فنی':kind==='legal'?'الزامات حقوقی و مجوزها':'بازبینی مستقل پیش از انتشار'}</h3>
    <ul className="docList">{ready.checks.filter(c=>c.kind===kind).map(c=><li key={c.key}><span className={'badge '+(c.passed?'':'warn')}>{c.passed?'تکمیل':'ناقص'}</span><span>{c.label}</span></li>)}</ul></div>)}
  </section>}
 </Shell>;
}
