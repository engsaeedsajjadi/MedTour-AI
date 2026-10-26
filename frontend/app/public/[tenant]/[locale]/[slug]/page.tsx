import type {Metadata} from 'next';
import Link from 'next/link';
import {notFound} from 'next/navigation';
import {PublicShell} from '@/components/PublicSite';
import {getManifest,getPage,isLocale,isTenant,isSlug,UI,publicPath,
 publicSiteOrigin,seoAllowed,type PublicLocale} from '@/lib/public-site';
type Params={tenant:string;locale:string;slug:string};
async function context(params:Promise<Params>){
 const {tenant,locale,slug}=await params;
 if(!isTenant(tenant)||!isLocale(locale)||!isSlug(slug))notFound();
 const manifest=await getManifest(tenant);
 if(!manifest||!manifest.pages.some(x=>x.slug===slug&&x.translations[locale]))notFound();
 const page=await getPage(tenant,locale,slug);
 if(!page||page.locale!==locale||page.slug!==slug)notFound();
 return {tenant,locale,slug,page,manifest};
}
export async function generateMetadata({params}:{params:Promise<Params>}):Promise<Metadata>{
 const {tenant,locale,slug,page,manifest}=await context(params);
 const origin=publicSiteOrigin();
 const translations=manifest.pages.find(x=>x.slug===slug)?.translations||{};
 const alternatives=Object.entries(translations).reduce<Record<string,string>>((out,[lng])=>{
  if(origin)out[lng]=origin+publicPath(tenant,lng as PublicLocale,slug);
  return out;
 },{});
 const summary=page.body.replace(/\s+/g,' ').slice(0,157);
 return {title:page.title+' | MedTour AI',description:summary,
  robots:seoAllowed(manifest)?{index:true,follow:true}:{index:false,follow:false},
  alternates:origin?{canonical:origin+publicPath(tenant,locale,slug),languages:alternatives}:undefined,
  openGraph:{title:page.title,description:summary,type:'article',
   locale,url:origin?origin+publicPath(tenant,locale,slug):undefined}};
}
export default async function PublishedPage({params}:{params:Promise<Params>}){
 const {tenant,locale,slug,page,manifest}=await context(params);
 const ui=UI[locale];
 const isLegal=['terms','privacy','medical-disclaimer'].includes(slug);
 return <PublicShell tenant={tenant} locale={locale} slug={slug} manifest={manifest}>
  <div className="site-inner-hero"><div className="site-wide">
   <Link className="site-backlink" href={publicPath(tenant,locale)}>{ui.brand} / {ui.nav[slug]||slug}</Link>
   <span className="site-overline">MEDTOUR / {slug.toUpperCase()}</span>
   <h1>{page.title}</h1><p>{ui.notVerified}</p>
  </div></div>
  <div className="site-wide site-article-wrap">
   <article className="site-article" lang={locale} dir={locale==='en'?'ltr':'rtl'}>
    {page.body.split(/\n\s*\n/g).map((paragraph,i)=>
     <p key={i} className="site-article-paragraph">{paragraph}</p>)}
   </article>
   <aside className="site-aside">
    <strong>{ui.legalTitle}</strong><p>{isLegal?ui.legalText:ui.notVerified}</p>
    {manifest.pages.some(p=>p.slug==='medical-disclaimer'&&p.translations[locale])&&slug!=='medical-disclaimer'&&
     <Link href={publicPath(tenant,locale,'medical-disclaimer')}>{ui.nav['medical-disclaimer']} ↗</Link>}
   </aside>
  </div>
 </PublicShell>;
}
