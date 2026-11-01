'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {useEffect,useState} from 'react';
import {getSession,logout,request} from '@/lib/api';
import {fa} from '@/lib/i18n';
import {allowedFor,homeFor} from '@/lib/roles';

const groups:{label:string;links:[string,string][]}[]=[
 {label:'پرتال',links:[['hospital-workspace','پرتال بیمارستان'],['physician-workspace','پرتال پزشک'],['doctor-cases','پرونده‌های مجاز پزشک'],['agent-portal','پرتال نماینده']]},
 {label:'نمای کلی',links:[['dashboard','داشبورد'],['admin-center','مرکز کنترل مدیریتی'],['modules','ماژول‌های یکپارچه']]},
 {label:'بیمار و پرونده',links:[['patients','بیماران'],['crm','مدیریت ارتباط بیمار'],['cases','پرونده‌ها'],['journey','مسیر بیمار'],['intake-review','پذیرش اولیه'],['intake-clinician','بازبینی تخصصی'],['secure-documents','مدارک پزشکی']]},
 {label:'ارائه‌دهندگان',links:[['providers','پزشکان'],['provider-matching','تطبیق ارائه‌دهندگان'],['physician-management','مدیریت پزشکان'],['hospitals','بیمارستان‌ها'],['hospital-management','مدیریت بیمارستان‌ها'],['appointments','نوبت‌ها']]},
 {label:'سفر و خدمات',links:[['travel','خدمات سفر'],['visa','ویزای درمانی'],['accommodation','اقامت و هتل'],['travel-coordination','ترانسفر و مترجم'],['operations','عملیات خدمات']]},
 {label:'ارتباطات',links:[['conversations','گفت‌وگوها'],['messaging','پیام‌رسانی و ترجمه'],['receptionist','منشی چندزبانه'],['voice','پردازش گفتار'],['ai-orchestration','دستیارهای هوشمند']]},
 {label:'مالی',links:[['quotations','پیش‌فاکتورها'],['prices','تعرفه‌ها'],['finance','تراکنش‌های مالی']]},
 {label:'محتوا و شبکه',links:[['agents','نمایندگان بین‌المللی'],['cms','محتوای وب‌سایت'],['cms-workflow','گردش‌کار محتوا'],['knowledge','پایگاه دانش']]},
 {label:'سازمان',links:[['reports','گزارش‌ها'],['staff','کاربران و دسترسی‌ها'],['settings','تنظیمات'],['tenant-isolation','ممیزی جداسازی سازمان‌ها'],['account-security','امنیت حساب']]},
];

const ENV_LABEL=process.env.NEXT_PUBLIC_ENV_LABEL||'نسخه نمایشی · فقط داده ساختگی';

export default function Shell({title,children}:{title:string,children:React.ReactNode}){
 const path=usePathname();
 const [email,setEmail]=useState(''),[role,setRole]=useState(''),[failed,setFailed]=useState(false);
 useEffect(()=>{
  if(!getSession()){window.location.replace('/login');return;}
  request<{email:string;role:string}>('/auth/me').then(x=>{setEmail(x.email);setRole(x.role);}).catch(()=>setFailed(true));
 },[]);
 const section=path.split('/')[1]||'';
 const permitted=role?allowedFor(role,section):false;
 const visible=groups.map(g=>({...g,links:g.links.filter(([href])=>allowedFor(role,href))})).filter(g=>g.links.length>0);
 return <div className="appShell">
  <a className="skipLink" href="#main-content">رفتن به محتوای اصلی</a>
  <aside className="sidebar" id="app-navigation">
   <div className="brand"><div className="brandMark" aria-hidden="true">✚</div><div><strong>MedTour AI</strong><small>مدیریت هوشمند گردشگری سلامت</small></div></div>
   <nav aria-label="ناوبری مدیریت">{visible.map(g=><div className="navGroup" key={g.label}>
    <div className="navGroupLabel">{g.label}</div>
    {g.links.map(([href,text])=>{const active=path==='/'+href||path.startsWith('/'+href+'/');
     return <Link aria-current={active?'page':undefined} className={active?'navItem selected':'navItem'} key={href} href={'/'+href}><span className="navDot" aria-hidden="true"/>{text}</Link>;})}
   </div>)}</nav>
   <div className="sidebarBottom"><span className="statusBullet" aria-hidden="true"/>{ENV_LABEL}</div>
  </aside>
  <main className="main" id="main-content" tabIndex={-1}>
   <header className="topbar">
    <div className="breadcrumb">MedTour AI <span>/</span> {title}</div>
    <div className="topActions">{role&&<span className="roleChip">{fa(role)}</span>}<span className="loggedIn" dir="ltr">{email}</span><button type="button" className="logout" onClick={logout}>خروج</button></div>
   </header>
   <div className="content">
    <div className="pageHeader"><div><div className="eyebrow">عملیات گردشگری سلامت</div><h1>{title}</h1></div><div className="environmentFlag">● {ENV_LABEL}</div></div>
    {failed?<div role="alert" className="errorBox">اطلاعات حساب دریافت نشد؛ صفحه را دوباره بارگذاری کنید.</div>
     :!role?<div className="panel loadingPanel" aria-busy="true">در حال بارگذاری…</div>
     :permitted?children
     :<section className="panel accessPanel" role="status"><h2>این بخش برای نقش شما در دسترس نیست</h2><p>نقش فعلی شما «{fa(role)}» است. اگر به این بخش نیاز دارید، از مدیر سازمان بخواهید دسترسی لازم را بدهد.</p><Link className="button" href={homeFor(role)}>رفتن به صفحه اصلی من</Link></section>}
   </div>
  </main>
 </div>;
}
