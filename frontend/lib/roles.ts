/** Which staff pages each role may open. The API still enforces every permission; this only shapes the interface. */

const PORTALS=['agent-portal','doctor-cases','physician-workspace','hospital-workspace'];
const ADMIN_ONLY=['admin-center','tenant-isolation','hospital-management','physician-management','agents','finance','reports','staff','settings','cms-workflow'];

export function allowedFor(role:string,href:string):boolean{
 if(!role)return false;
 if(href==='account-security')return true;
 if(role==='admin')return !PORTALS.includes(href);
 if(role==='operator')return !PORTALS.includes(href)&&!ADMIN_ONLY.includes(href);
 if(role==='hospital')return href==='hospital-workspace';
 if(role==='physician')return href==='physician-workspace';
 if(role==='doctor')return href==='doctor-cases';
 if(role==='agent')return href==='agent-portal';
 if(role.startsWith('cms_'))return href==='cms-workflow';
 return false;
}

/** Landing page after sign-in, so each role starts on a page it can use. */
export function homeFor(role:string):string{
 if(role==='hospital')return '/hospital-workspace';
 if(role==='physician')return '/physician-workspace';
 if(role==='doctor')return '/doctor-cases';
 if(role==='agent')return '/agent-portal';
 if(role.startsWith('cms_'))return '/cms-workflow';
 if(role==='admin'||role==='operator')return '/dashboard';
 return '/account-security';
}
