import {NextRequest,NextResponse} from 'next/server';
import {getManifest,publicSiteOrigin,publicPath,
 seoAllowed,PUBLIC_LOCALES,type PublicLocale} from '@/lib/public-site';

function escapeXml(s:string){return s.replace(/[&<>"']/g,c=>({
 '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'
}[c]||c));}
export async function GET(_request:NextRequest,{params}:{
 params:Promise<{tenant:string}>
}){
 const {tenant}=await params,manifest=await getManifest(tenant);
 if(!manifest||!seoAllowed(manifest))return new NextResponse('Not available',{status:404,headers:{'Cache-Control':'no-store'}});
 const origin=publicSiteOrigin();
 if(!origin)return new NextResponse('Not available',{status:404});
 const urls:string[]=[];
 for(const locale of PUBLIC_LOCALES){
  urls.push(origin+publicPath(tenant,locale));
  for(const entry of manifest.pages){
   if(entry.translations[locale])urls.push(origin+publicPath(tenant,locale,entry.slug));
  }
 }
 const entries=urls.map(x=>'<url><loc>'+escapeXml(x)+'</loc></url>').join('');
 const body='<?xml version="1.0" encoding="UTF-8"?>'+
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+entries+'</urlset>';
 return new NextResponse(body,{status:200,headers:{
  'Content-Type':'application/xml; charset=utf-8',
  'Cache-Control':'public, max-age=0, s-maxage=300',
  'X-Content-Type-Options':'nosniff'
 }});
}
