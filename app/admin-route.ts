const SECTIONS: Record<string, string> = {
  categories: 'categories',
  traders: 'merchants',
  products: 'products',
  'price-lists': 'prices',
  currencies: 'currencies',
  orders: 'orders',
  invoices: 'invoices',
  settings: 'settings',
};

const SLUGS: Record<string, string> = Object.fromEntries(Object.entries(SECTIONS).map(([slug, tab]) => [tab, slug]));

export type AdminRoute = {tab: string; traderId: string | null};

export function readAdminRoute(hash: string): AdminRoute | null {
  const raw = hash.replace(/^#/, '').split('?')[0];
  if (raw === 'admin') return {tab: 'overview', traderId: null};
  if (!raw.startsWith('admin/')) return null;
  const [, section = '', traderId = ''] = raw.split('/');
  if (section === 'traders') return {tab: 'merchants', traderId: traderId ? decodeURIComponent(traderId) : null};
  return {tab: SECTIONS[section] || 'overview', traderId: null};
}

export function adminHref(tab: string, traderId?: string | null) {
  if (tab === 'merchants' && traderId) return `#admin/traders/${encodeURIComponent(traderId)}`;
  if (tab === 'overview') return '#admin';
  return `#admin/${SLUGS[tab] || 'overview'}`;
}
