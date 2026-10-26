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
export default function TenantIsolation(){
 const [state,setState]=useState<Status|null>(null);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 async function refresh(){
  setLoading(true);setError('');
  try{const s=await request<Status>('/admin/tenant-isolation/status');setState(s);}
  catch(e){setError((e as Error).message);}finally{setLoading(false);}
 }
 useEffect(()=>{void refresh();},[]);
 const values=[
  ['جدول‌های Tenantدار',state?.tenant_scoped_tables??'-'],
  ['کلیدهای خارجی مرکب',state?.composite_tenant_fks??'-'],
  ['جدول‌های دارای سیاست RLS',state?.rls_policy_tables??'-'],
  ['جدول‌های FORCE RLS در دیتابیس فعلی',state?.rls_force_tables??'-']
 ];
 return <Shell title="ممیزی جداسازی سازمان‌ها">
  <div className="infoBanner">وضعیت بخش ۲۶: ساختار کلیدهای مرکب و سیاست‌های RLS آماده شده‌اند، اما این صفحه مجوز استفاده از اطلاعات پزشکی واقعی یا استقرار تجاری نیست. فعال‌سازی RLS در دیتابیس فعلی باید تنها پس از انتقال کامل Login/Refresh، پرتال، وب‌هوک و Worker به نقش‌های مستقل Tenant انجام شود.</div>
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
     <p>هویت Tenant مستقل از اتصال: <strong>{state?.authenticated_tenant_role?'تأیید شده':'هنوز متصل نشده'}</strong></p>
     <p>مسیریابی تمام Endpointها: <strong>{state?.verified_end_to_end_routing?'تأیید شده':'ناقص'}</strong></p>
     <p>آمادگی Production: <strong>{state?.production_ready?'تأیید شده':'خیر'}</strong></p>
     <p>{state?.reason}</p>
    </div>
   </>}
   <button className="button" style={{marginTop:14}} disabled={loading} onClick={()=>void refresh()}>بررسی مجدد</button>
  </section>
 </Shell>;
}
