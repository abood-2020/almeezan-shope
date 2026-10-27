import type { MetadataRoute } from 'next';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const SITE_URL = 'https://algharabligloba.com';

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\u0621-\u064A-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'product';
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticUrls: MetadataRoute.Sitemap = [
    {
      url: `${SITE_URL}/`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1.0,
    },
    {
      url: `${SITE_URL}/#catalog`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 0.9,
    },
    {
      url: `${SITE_URL}/#traders`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 0.7,
    },
    {
      url: `${SITE_URL}/#contact`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.6,
    },
  ];

  try {
    const res = await fetch(`${API_BASE}/api/catalog/products/`, { next: { revalidate: 3600 } });
    if (!res.ok) return staticUrls;
    const products = await res.json() as Array<{ id: number; name_en?: string; name_ar?: string; is_archived?: boolean; updated_at?: string }>;

    const productUrls: MetadataRoute.Sitemap = products
      .filter(p => !p.is_archived)
      .map(p => {
        const slug = slugify(p.name_en || p.name_ar || `item-${p.id}`);
        return {
          url: `${SITE_URL}/products/${p.id}-${slug}`,
          lastModified: p.updated_at ? new Date(p.updated_at) : new Date(),
          changeFrequency: 'weekly',
          priority: 0.8,
        };
      });

    return [...staticUrls, ...productUrls];
  } catch {
    return staticUrls;
  }
}
