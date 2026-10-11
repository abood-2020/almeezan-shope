import type {Product} from './data';

export type CategoryRef = {id?: number; ar: string; en: string; parentId?: number | null; level?: number};
export type CatalogNode = {id: number; ar: string; en: string; count: number; level: number; children: CatalogNode[]};
export type CatalogGroup = CatalogNode;

export function descendantIds(categories: CategoryRef[], selectedId: number) {
  const ids = new Set<number>();
  const walk = (id: number) => {
    if (!id || ids.has(id)) return;
    ids.add(id);
    categories.forEach(category => {
      if (category.parentId === id && category.id) walk(category.id);
    });
  };
  walk(selectedId);
  return ids;
}

export function catalogTree(categories: CategoryRef[], products: Product[]): CatalogNode[] {
  const countFor = (id: number) => products.filter(product => descendantIds(categories, id).has(categories[product.cat]?.id || 0)).length;
  const nodes = (parentId: number | null, level: number): CatalogNode[] => categories.flatMap(category => {
    if (!category.id || (category.parentId ?? null) !== parentId) return [];
    return [{
      id: category.id,
      ar: category.ar,
      en: category.en,
      level,
      count: countFor(category.id),
      children: level < 3 ? nodes(category.id, level + 1) : [],
    }];
  });
  return nodes(null, 1);
}

export const catalogHref = (category = 0, _subcategory = '') => category ? `#products?category=${category}` : '#products';

function nodeById(nodes: CatalogNode[], id: number): CatalogNode | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    const child = nodeById(node.children, id);
    if (child) return child;
  }
  return undefined;
}

export function readStoreRoute(hash: string, groups: CatalogNode[]) {
  const [raw, search = ''] = hash.replace(/^#/, '').split('?');
  const page = ['home', 'products', 'cart', 'portal', 'admin', 'confirmation', 'info', 'traders', 'export', 'contact'].includes(raw) ? raw : 'home';
  const params = new URLSearchParams(search);
  const requested = [params.get('detail'), params.get('subcategory'), params.get('category')]
    .map(value => Number(value || 0))
    .find(id => id && nodeById(groups, id));
  return {page, category: requested || 0, subcategory: ''};
}
