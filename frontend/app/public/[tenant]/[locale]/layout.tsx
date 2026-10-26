import type {ReactNode} from 'react';
import {notFound} from 'next/navigation';
import {isLocale,isTenant} from '@/lib/public-site';
import './site.css';
export default async function SiteLocaleLayout({
 children,params
}:{children:ReactNode;params:Promise<{tenant:string;locale:string}>}){
 const {tenant,locale}=await params;
 if(!isTenant(tenant)||!isLocale(locale))notFound();
 return children;
}
