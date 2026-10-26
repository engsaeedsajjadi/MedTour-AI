import {NextResponse,type NextRequest} from 'next/server';
export function proxy(request:NextRequest){
 const parts=request.nextUrl.pathname.split('/');
 const locale=parts[1]==='public'?parts[3]:'';
 const headers=new Headers(request.headers);
 if(locale==='en'||locale==='fa'||locale==='ar')
  headers.set('x-medtour-public-locale',locale);
 return NextResponse.next({request:{headers}});
}
export const config={matcher:['/public/:path*']};
