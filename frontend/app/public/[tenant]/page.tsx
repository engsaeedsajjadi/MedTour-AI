import {headers} from 'next/headers';
import {notFound,redirect} from 'next/navigation';
import {getManifest,isTenant,publicPath,type PublicLocale} from '@/lib/public-site';
function bestLocale(value:string):PublicLocale{
 const preferences=value.split(',').map(x=>{
  const [tag,...params]=x.trim().toLowerCase().split(';');
  const qPart=params.find(p=>p.trim().startsWith('q='));
  const q=qPart?Number(qPart.trim().slice(2)):1;
  return {tag,q:Number.isFinite(q)&&q>=0&&q<=1?q:0};
 }).sort((a,b)=>b.q-a.q);
 for(const {tag,q} of preferences){
  if(q===0)continue;
  if(tag==='fa-af'||tag==='prs'||tag.startsWith('prs-'))return 'prs';
  if(tag==='ps'||tag.startsWith('ps-'))return 'ps';
  if(tag==='ar'||tag.startsWith('ar-'))return 'ar';
  if(tag==='fa'||tag.startsWith('fa-'))return 'fa';
  if(tag==='en'||tag.startsWith('en-'))return 'en';
 }
 return 'en';
}
export default async function PublicEntry({params}:{params:Promise<{tenant:string}>}){
 const {tenant}=await params;
 if(!isTenant(tenant)||!await getManifest(tenant))notFound();
 const userHeaders=await headers();
 redirect(publicPath(tenant,bestLocale(userHeaders.get('accept-language')||'')));
}
