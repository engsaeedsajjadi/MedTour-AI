import Link from 'next/link';
import ResourcePage from '@/components/ResourcePage';
export default function Hospitals(){return <ResourcePage title="بیمارستان‌ها" path="/hospitals" fields={[{name:'name',label:'نام مرکز',required:true},{name:'city',label:'شهر'}]}
 columns={[{key:'name',label:'نام مرکز'},{key:'city',label:'شهر'},{key:'license_status',label:'وضعیت داخلی فهرست'}]}
 intro={<>برای ثبت مدارک، خدمات و حساب کارکنان هر مرکز از <Link href="/hospital-management">مدیریت بیمارستان‌ها</Link> استفاده کنید.</>}
 note="وضعیت اولیه هر مرکز «تأییدنشده» است. بررسی محلی مدارک به معنی استعلام مستقل مجوز بیمارستان نیست."/>;}
