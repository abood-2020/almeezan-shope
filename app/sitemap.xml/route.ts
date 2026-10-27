const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const SITE_URL = 'https://algharabligloba.com';

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\u0621-\u064A-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'product';
}

function escapeXml(unsafe: string): string {
  return unsafe.replace(/[<>&'"]/g, (c) => {
    switch (c) {
      case '<': return '&lt;';
      case '>': return '&gt;';
      case '&': return '&amp;';
      case '\'': return '&apos;';
      case '"': return '&quot;';
      default: return c;
    }
  });
}

export async function GET() {
  const urls: Array<{ loc: string; lastmod?: string; changefreq: string; priority: string }> = [
    { loc: `${SITE_URL}/`, changefreq: 'daily', priority: '1.0' },
    { loc: `${SITE_URL}/#catalog`, changefreq: 'daily', priority: '0.9' },
    { loc: `${SITE_URL}/#traders`, changefreq: 'weekly', priority: '0.7' },
    { loc: `${SITE_URL}/#contact`, changefreq: 'monthly', priority: '0.6' },
  ];

  try {
    const res = await fetch(`${API_BASE}/api/catalog/products/`, { cache: 'no-store' });
    if (res.ok) {
      const products = await res.json() as Array<{ id: number; name_en?: string; name_ar?: string; is_archived?: boolean; updated_at?: string }>;
      for (const p of products) {
        if (p.is_archived) continue;
        const slug = slugify(p.name_en || p.name_ar || `item-${p.id}`);
        urls.push({
          loc: `${SITE_URL}/products/${p.id}-${slug}`,
          lastmod: p.updated_at ? new Date(p.updated_at).toISOString().split('T')[0] : new Date().toISOString().split('T')[0],
          changefreq: 'weekly',
          priority: '0.8',
        });
      }
    }
  } catch {
    // fallback to static URLs
  }

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls
  .map(
    (u) => `  <url>
    <loc>${escapeXml(u.loc)}</loc>
    ${u.lastmod ? `<lastmod>${u.lastmod}</lastmod>` : ''}
    <changefreq>${u.changefreq}</changefreq>
    <priority>${u.priority}</priority>
  </url>`
  )
  .join('\n')}
</urlset>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}
