import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'رِواق | أزياء الجملة للتجار',description:'اكتشف تشكيلة رِواق للملابس بالجملة، راجع الألوان والمقاسات وأرسل طلبك التجاري. العربية والإنجليزية.',icons:{icon:'/favicon.svg',shortcut:'/favicon.svg'}};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="ar" dir="rtl"><body>{children}</body></html>}
