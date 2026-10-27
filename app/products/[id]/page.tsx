import type { Metadata } from 'next';
import ProductDetailClient from './product-client';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const SITE_URL = 'https://algharabligloba.com';

function parseId(param: string): number {
  const match = param.match(/^(\d+)/);
  return match ? parseInt(match[1], 10) : 0;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\u0621-\u064A-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'product';
}

function resolveMediaUrl(src: string): string {
  if (!src) return `${SITE_URL}/assets/women.jpg`;
  if (src.startsWith('http://') || src.startsWith('https://')) return src;
  if (src.startsWith('/media/')) return `${API_BASE}${src}`;
  if (src.startsWith('/')) return `${SITE_URL}${src}`;
  return `${SITE_URL}/assets/${src}.jpg`;
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id: rawId } = await params;
  const id = parseId(rawId);

  try {
    const res = await fetch(`${API_BASE}/api/catalog/products/${id}/`, { cache: 'no-store' });
    if (!res.ok) {
      return {
        title: 'المنتج غير متوفر | الغرابلي جلوبال',
        description: 'هذا المنتج غير متوفر في الكتالوج حاليًا.',
      };
    }
    const product = await res.json();
    if (product.is_archived) {
      return {
        title: 'المنتج غير متوفر | الغرابلي جلوبال',
        description: 'تمت أرشفة هذا المنتج وهو غير متاح للطلب.',
      };
    }

    const nameAr = product.name_ar || 'منتج';
    const nameEn = product.name_en || 'Product';
    const desc = product.description_ar || product.description_en || 'أزياء وملابس جملة للتجار - الغرابلي جلوبال';
    const slug = slugify(product.name_en || product.name_ar || `item-${id}`);
    const canonical = `${SITE_URL}/products/${id}-${slug}`;
    const primaryImg = resolveMediaUrl(product.image || product.gallery?.[0] || '');

    return {
      title: `${nameAr} | ${nameEn} | الغرابلي جلوبال`,
      description: desc,
      alternates: {
        canonical,
      },
      openGraph: {
        title: `${nameAr} - الغرابلي جلوبال`,
        description: desc,
        url: canonical,
        siteName: 'الغرابلي جلوبال - Algharabli Global',
        locale: 'ar',
        type: 'website',
        images: [
          {
            url: primaryImg,
            width: 1200,
            height: 630,
            alt: nameAr,
          },
        ],
      },
      twitter: {
        card: 'summary_large_image',
        title: `${nameAr} | الغرابلي جلوبال`,
        description: desc,
        images: [primaryImg],
      },
    };
  } catch {
    return {
      title: 'الغرابلي جلوبال | أزياء الجملة للتجار',
      description: 'أزياء وملابس جملة للتجار - الغرابلي جلوبال',
    };
  }
}

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: rawId } = await params;
  const id = parseId(rawId);

  let product: any = null;
  let categories: any[] = [];
  try {
    const [pRes, cRes] = await Promise.all([
      fetch(`${API_BASE}/api/catalog/products/${id}/`, { cache: 'no-store' }),
      fetch(`${API_BASE}/api/catalog/categories/`, { cache: 'no-store' }),
    ]);
    if (pRes.ok) {
      product = await pRes.json();
    }
    if (cRes.ok) {
      categories = await cRes.json();
    }
  } catch {
    // handled in client component
  }

  const slug = product ? slugify(product.name_en || product.name_ar || `item-${id}`) : '';
  const canonicalUrl = `${SITE_URL}/products/${id}${slug ? `-${slug}` : ''}`;
  const primaryImg = product ? resolveMediaUrl(product.image || product.gallery?.[0] || '') : '';

  const jsonLd = product && !product.is_archived
    ? {
        '@context': 'https://schema.org',
        '@type': 'Product',
        name: product.name_ar,
        image: primaryImg,
        description: product.description_ar || product.description_en || '',
        sku: product.code,
        offers: {
          '@type': 'Offer',
          url: canonicalUrl,
          priceCurrency: 'ILS',
          price: product.price || product.base_price_ils || '0.00',
          availability: product.available ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock',
        },
      }
    : null;

  return (
    <>
      {jsonLd && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      )}
      <ProductDetailClient
        initialProduct={product}
        productId={id}
        canonicalUrl={canonicalUrl}
        categories={categories}
      />
    </>
  );
}
