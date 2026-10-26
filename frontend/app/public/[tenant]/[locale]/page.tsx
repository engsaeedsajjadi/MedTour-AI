import type {Metadata} from 'next';
import Link from 'next/link';
import {notFound} from 'next/navigation';
import {PublicShell} from '@/components/PublicSite';
import {UI,getManifest,isLocale,isTenant,publicPath,hasPage,
 seoAllowed,publicSiteOrigin,PUBLIC_LOCALES,type PublicLocale} from '@/lib/public-site';
type Params={tenant:string;locale:string};
const slugs=['services','about','process','faq','contact'] as const;
async function context(params:Promise<Params>){
 const {tenant,locale}=await params;
 if(!isTenant(tenant)||!isLocale(locale))notFound();
 const manifest=await getManifest(tenant);
 if(!manifest)notFound();
 return {tenant,locale,manifest};
}
export async function generateMetadata({params}:{params:Promise<Params>}):Promise<Metadata>{
 const {tenant,locale,manifest}=await context(params);
 const copy=UI[locale];
 const origin=publicSiteOrigin();
 const robots:Metadata['robots']=seoAllowed(manifest)?{index:true,follow:true}:{index:false,follow:false};
 return {
  title:copy.heroTitle+' | MedTour AI',
  description:copy.heroLine.slice(0,160),
  robots,
  alternates:origin?{
   canonical:origin+publicPath(tenant,locale),
   languages:Object.fromEntries(PUBLIC_LOCALES.map(l=>[l,origin+publicPath(tenant,l)]))
  }:undefined,
  openGraph:{title:copy.heroTitle,description:copy.heroLine.slice(0,160),
   locale, type:'website',siteName:'MedTour AI',url:origin?origin+publicPath(tenant,locale):undefined}
 };
}
export default async function SiteHome({params}:{params:Promise<Params>}){
 const {tenant,locale,manifest}=await context(params);
 const ui=UI[locale];
 const published=slugs.filter(s=>hasPage(manifest,s,locale));
 const words:Record<PublicLocale,string[]>={fa:['آگاهی','رضایت','همراهی'],
  ar:['الوضوح','الموافقة','المتابعة'],en:['Clarity','Consent','Coordination']};
 return <PublicShell tenant={tenant} locale={locale} manifest={manifest}>
  <section className="site-hero">
   <div className="site-wide site-hero-grid">
    <div className="site-hero-copy">
     <span className="site-status"><span className="site-dot"/> {ui.badge}</span>
     <h1>{ui.heroTitle}</h1>
     <p className="site-hero-lede">{ui.heroLine}</p>
     <div className="site-hero-actions">
      {hasPage(manifest,'process',locale)&&<Link className="site-cta" href={publicPath(tenant,locale,'process')}>{ui.start}<span aria-hidden>←</span></Link>}
      {hasPage(manifest,'services',locale)&&<Link className="site-cta-outline" href={publicPath(tenant,locale,'services')}>{ui.learn}</Link>}
     </div>
     <div className="site-hero-footnotes"><span>◈ {ui.heroStat1}</span><span>◈ {ui.heroStat2}</span></div>
    </div>
    <div className="site-hero-art" aria-hidden="true">
     <div className="site-orb-ring ring-a"/><div className="site-orb-ring ring-b"/>
     <div className="site-art-core"><span>✳</span><strong>MedTour</strong><small>CARE COORDINATION</small></div>
     <div className="site-art-float float-a">✦ {words[locale][0]}</div>
     <div className="site-art-float float-b">◉ {words[locale][1]}</div>
     <div className="site-art-float float-c">⇄ {words[locale][2]}</div>
    </div>
   </div>
  </section>
  <section className="site-feature-section">
   <div className="site-wide">
    <div className="site-section-heading"><span className="site-overline">01 / THE JOURNEY</span><h2>{ui.stepsTitle}</h2><p>{ui.intro}</p></div>
    <div className="site-steps">
     {ui.stepDescriptions.map((label,index)=><div className="site-step" key={index}>
      <span className="site-step-num">{String(index+1).padStart(2,'0')}</span>
      <p>{label}</p></div>)}
    </div>
   </div>
  </section>
  <section className="site-content-section">
   <div className="site-wide">
    <div className="site-section-heading"><span className="site-overline">02 / INFORMATION</span><h2>{ui.servicesTitle}</h2></div>
    {published.length?<div className="site-service-grid">{published.map((slug,index)=>{
     const page=manifest.pages.find(p=>p.slug===slug)?.translations[locale];
     if(!page)return null;
     return <Link className="site-service-card" key={slug} href={publicPath(tenant,locale,slug)}>
      <span className="site-card-mark">{['✳','◎','⇄','?','✦'][index]}</span>
      <h3>{page.title}</h3>
      <p>{page.summary}</p>
      <span className="site-card-more" aria-hidden>↗</span>
     </Link>;
    })}</div>:<div className="site-empty">{ui.missing}</div>}
   </div>
  </section>
  <section className="site-disclosure">
   <div className="site-wide site-disclosure-inner">
    <div><span className="site-overline">03 / TRUST & TRANSPARENCY</span><h2>{ui.legalTitle}</h2><p>{ui.legalText}</p></div>
    <div className="site-disclosure-symbol" aria-hidden>◇</div>
   </div>
  </section>
 </PublicShell>;
}
