import Link from 'next/link';
import type {ReactNode} from 'react';
import {PUBLIC_LOCALES,UI,publicPath,hasPage,type PublicLocale,type PublicManifest} from '@/lib/public-site';

export function PublicShell({tenant,locale,manifest,slug,children}:{
 tenant:string;locale:PublicLocale;manifest:PublicManifest;slug?:string;children:ReactNode;
}){
 const ui=UI[locale];
 const sections=['about','services','process','faq','contact'];
 const legal=['privacy','terms','medical-disclaimer'];
 const dir=locale==='en'?'ltr':'rtl';
 return <div className="site-shell" dir={dir} lang={locale}>
  <a className="site-skip" href="#site-main">{locale==='en'?'Skip to content':locale==='ar'?'تخطَّ إلى المحتوى':'رفتن به محتوا'}</a>
  <header className="site-header">
   <div className="site-wide site-header-inner">
    <Link className="site-logo" href={publicPath(tenant,locale)} aria-label={ui.brand+' home'}>
     <span className="site-emblem" aria-hidden="true">✳</span>
     <span className="site-logo-text"><strong>{ui.brand}</strong><small>{ui.tagline}</small></span>
    </Link>
    <nav className="site-main-nav" aria-label="Main navigation">
     {sections.filter(s=>hasPage(manifest,s,locale)).map(s=>
      <Link key={s} aria-current={slug===s?'page':undefined}
        href={publicPath(tenant,locale,s)}>{ui.nav[s]}</Link>)}
    </nav>
    <div className="site-language" aria-label={ui.language}>
     {PUBLIC_LOCALES.map(l=>{
      const href=slug&&hasPage(manifest,slug,l)?publicPath(tenant,l,slug):publicPath(tenant,l);
      return <Link key={l} href={href} hrefLang={l} lang={l} aria-label={l}
        aria-current={l===locale?'page':undefined}>{l==='fa'?'FA':l==='ar'?'AR':'EN'}</Link>;
     })}
    </div>
   </div>
  </header>
  <main id="site-main">{children}</main>
  <footer className="site-footer">
   <div className="site-wide site-footer-top">
    <div><strong className="site-footer-brand">✳ MedTour AI</strong><p>{ui.footer}</p>
    <p className="site-safe-note">{ui.notVerified}</p></div>
    <nav className="site-footer-links" aria-label="Legal navigation">
     {legal.filter(s=>hasPage(manifest,s,locale)).map(s=>
      <Link href={publicPath(tenant,locale,s)} key={s}>{ui.nav[s]}</Link>)}
    </nav>
   </div>
   <div className="site-wide site-footer-bottom">
     <span>© MedTour AI · Alpha demonstration</span>
     <span>{manifest.all_languages_complete?'3 / 3 locales published':'Content and translations pending review'}</span>
   </div>
  </footer>
 </div>;
}
