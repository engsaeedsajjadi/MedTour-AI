'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {useEffect,useState} from 'react';
import {getSession,logout,request} from '@/lib/api';
const links=[
 ['dashboard','داشبورد'],['patients','بیماران'],['cases','پرونده‌ها'],['providers','پزشکان'],['hospitals','بیمارستان‌ها'],['quotations','پیش‌فاکتورها'],['appointments','نوبت‌ها'],['travel','سفر و ویزا'],['conversations','گفت‌وگوها'],['messaging','پیام‌رسانی و ترجمه'],['operations','عملیات خدمات'],['agents','نمایندگان'],['prices','تعرفه‌ها'],['finance','مالی'],['cms','محتوا'],['knowledge','پایگاه دانش'],['secure-documents','مدارک'],['reports','گزارش‌ها'],['staff','کاربران'],['saas','اشتراک سازمان'],['settings','تنظیمات']
] as const;
export default function Shell({title,children}:{title:string,children:React.ReactNode}){
 const path=usePathname();const [email,setEmail]=useState('');
 useEffect(()=>{if(!getSession()){window.location.replace('/login');return;}request<{email:string}>('/auth/me').then(x=>setEmail(x.email)).catch(()=>{});},[]);
 return <div className="appShell"><aside className="sidebar"><div className="brand"><div className="brandMark">✚</div><div><strong>MedTour AI</strong><small>International Patient Care</small></div></div><div className="navGroupLabel">سامانه مدیریت</div><nav>{links.map(([href,text])=><Link className={path.startsWith('/'+href)?'navItem selected':'navItem'} key={href} href={'/'+href}><span className="navDot"/>{text}</Link>)}</nav><div className="sidebarBottom"><span className="statusBullet"/> محیط توسعه — بدون داده واقعی بیمار</div></aside>
 <main className="main"><header className="topbar"><div className="breadcrumb">MedTour AI <span>/</span> {title}</div><div className="topActions"><span className="loggedIn">{email}</span><button className="logout" onClick={logout}>خروج</button></div></header><div className="content"><div className="pageHeader"><div><div className="eyebrow">MEDICAL TOURISM OPERATIONS</div><h1>{title}</h1></div><div className="environmentFlag">● DEVELOPMENT · NOT FOR REAL PATIENTS</div></div>{children}</div></main></div>;
}
