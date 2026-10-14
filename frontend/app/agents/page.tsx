'use client';
import ResourcePage from '@/components/ResourcePage';
export default function Agents(){return <ResourcePage title="نمایندگان خارجی" path="/agents" fields={[{name:'name',label:'نام نماینده',required:true},{name:'country',label:'کشور',required:true}]} columns={[{key:'id',label:'شناسه'},{key:'name',label:'نماینده'},{key:'country',label:'کشور'},{key:'referral_code',label:'کد ارجاع'}]} note="فقط مدیر می‌تواند نماینده اضافه کند. پرداخت حق‌الزحمه نیازمند قرارداد و بررسی ضوابط است."/>}
