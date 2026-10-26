import type {Metadata} from 'next';
import {headers} from 'next/headers';
import './styles.css';
export const metadata:Metadata={title:'MedTour AI | پنل مدیریت گردشگری سلامت',description:'پلتفرم مدیریت هماهنگی بیماران بین‌المللی'};
export default async function RootLayout({children}:{children:React.ReactNode}){
 const headerStore=await headers();
 const fromPublic=headerStore.get('x-medtour-public-locale');
 const lang=fromPublic==='en'||fromPublic==='ar'||fromPublic==='fa'||fromPublic==='ps'||fromPublic==='prs'?fromPublic:'fa';
 return <html lang={lang} dir={lang==='en'?'ltr':'rtl'}><body>{children}</body></html>;
}
