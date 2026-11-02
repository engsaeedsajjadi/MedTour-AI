'use client';
import Link from 'next/link';
import Shell from './Shell';

/** Common frame for the sub-pages of Settings: breadcrumb back to Settings, messages and content. */
export default function SettingsPageFrame({title,intro,error,notice,children}:{title:string,intro:string,error:string,notice:string,children:React.ReactNode}){
 return <Shell title={title}>
  <p className="settingsBack"><Link className="textLink" href="/settings?tab=base">← بازگشت به تنظیمات</Link></p>
  <div className="infoBanner">{intro}</div>
  {error&&<div className="errorBox" role="alert">{error}</div>}
  {notice&&<div className="infoBanner" role="status">{notice}</div>}
  {children}
 </Shell>;
}
