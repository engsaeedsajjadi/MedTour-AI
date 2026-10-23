import Link from 'next/link';
import ResourcePage from '@/components/ResourcePage';
export default function Hospitals(){return <>
 <div className="infoBanner">فهرست مراکز برای داده‌های ساختگی است. تأیید قدیمی فهرست به معنی استعلام مستقل مجوز نیست. برای بررسی محلی مدارک، خدمات و پرتال از <Link href="/hospital-management">مدیریت بیمارستان‌ها</Link> استفاده کنید.</div>
 <ResourcePage title="بیمارستان‌ها" path="/hospitals" fields={[{name:'name',label:'نام مرکز',required:true},{name:'city',label:'شهر'}]}
 columns={[{key:'name',label:'نام مرکز'},{key:'city',label:'شهر'},{key:'license_status',label:'وضعیت داخلی فهرست'}]}
 note="وضعیت اولیه تأییدنشده است. بررسی محلی به منزله استعلام مستقل مجوز بیمارستان نیست."/>
 </>;}
