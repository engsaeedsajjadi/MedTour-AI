'use client';
import {useEffect,useState} from 'react';
import ResourcePage from '@/components/ResourcePage';
import {cachedOrganization,loadOrganization} from '@/lib/preferences';
export default function Patients(){
 // Only the languages the organization enabled in Settings are offered (the API enforces the same list).
 const [languages,setLanguages]=useState<string[]>(['fa','ar','en','ps','prs']);
 useEffect(()=>{const c=cachedOrganization();if(c)setLanguages(c.enabled_languages);
  loadOrganization().then(o=>setLanguages(o.profile.enabled_languages)).catch(()=>{});},[]);
 return <ResourcePage title="بیماران" path="/patients" fields={[{name:'full_name',label:'نام بیمار',required:true},{name:'country',label:'کشور'},{name:'language',label:'زبان',type:'select',options:languages,required:true},{name:'contact',label:'اطلاعات تماس'}]} columns={[{key:'full_name',label:'نام'},{key:'country',label:'کشور'},{key:'language',label:'زبان'},{key:'contact',label:'تماس'},{key:'id',label:'شناسه'}]} showIntakeConsent note="برای ایجاد پرونده ابتدا لینک رضایت پذیرش را صادر و در صفحه مخصوص بیمار آزمایشی پاسخ دهید؛ از داده واقعی استفاده نکنید."/>;}
