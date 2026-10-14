import type { Metadata } from 'next';
import './styles.css';
export const metadata:Metadata={title:'MedTour AI | پنل مدیریت گردشگری سلامت',description:'پلتفرم مدیریت هماهنگی بیماران بین‌المللی'};
export default function RootLayout({children}:{children:React.ReactNode}){
 return <html lang="fa" dir="rtl"><body>{children}</body></html>;
}
