import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://algharabligloba.com'),
  title: {
    default: 'الغرابلي جلوبال | أزياء الجملة للتجار',
    template: '%s | الغرابلي جلوبال',
  },
  description: 'اكتشف تشكيلة الغرابلي جلوبال للملابس بالجملة، راجع الألوان والمقاسات وأرسل طلبك التجاري. العربية والإنجليزية.',
  alternates: {
    canonical: 'https://algharabligloba.com/',
  },
  icons: { icon: '/favicon.svg', shortcut: '/favicon.svg' },
  openGraph: {
    title: 'الغرابلي جلوبال | أزياء الجملة للتجار',
    description: 'اكتشف تشكيلة الغرابلي جلوبال للملابس بالجملة، راجع الألوان والمقاسات وأرسل طلبك التجاري.',
    url: 'https://algharabligloba.com',
    siteName: 'الغرابلي جلوبال - Algharabli Global',
    locale: 'ar',
    type: 'website',
    images: [
      {
        url: 'https://algharabligloba.com/assets/women.jpg',
        width: 1200,
        height: 630,
        alt: 'الغرابلي جلوبال - أزياء الجملة',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'الغرابلي جلوبال | أزياء الجملة للتجار',
    description: 'اكتشف تشكيلة الغرابلي جلوبال للملابس بالجملة، راجع الألوان والمقاسات وأرسل طلبك التجاري.',
    images: ['https://algharabligloba.com/assets/women.jpg'],
  },
};

export default function Layout({children}:{children:React.ReactNode}){
  return <html lang="ar" dir="rtl"><body>{children}</body></html>;
}
