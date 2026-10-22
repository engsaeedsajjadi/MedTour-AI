'use client';
import ResourcePage from '@/components/ResourcePage';
export default function Staff(){return <ResourcePage title="کاربران و دسترسی‌ها" path="/staff" fields={[{name:'email',label:'ایمیل',required:true},{name:'password',label:'رمز قوی اولیه (۱۲ نویسه یا بیشتر)',required:true},{name:'role',label:'نقش',type:'select',options:['operator','auditor','admin','physician'],required:true}]} columns={[{key:'id',label:'شناسه'},{key:'email',label:'ایمیل'},{key:'role',label:'نقش'},{key:'active',label:'فعال'}]} note="برای محیط واقعی باید فرآیند دعوت امن و MFA جایگزین ارسال رمز اولیه شود."/>}
