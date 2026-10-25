import {api, fileFromBlob, resolveMedia} from "./api";
import type {CartLine, Order, Product} from "./data";
import type {PriceList} from "./pricing";

export type ApiCategory = {id: number; name_ar: string; name_en: string; image: string; parent_id?: number | null; level?: number; children?: number[]};
export type ApiColor = {id?: number; name_ar: string; name_en: string; hex: string; image: string};
export type ApiImage = {id: number; url: string; image_key: string; sort_order: number; is_primary: boolean};
export type ApiProduct = {
  id: number;
  name_ar: string;
  name_en: string;
  code: string;
  category_id: number;
  unit_ar: string;
  unit_en: string;
  min_qty: number;
  available: boolean;
  is_archived?: boolean;
  description_ar: string;
  description_en: string;
  badge: string;
  image: string;
  gallery: string[];
  colors: ApiColor[];
  sizes: string[];
  options: string[];
  unavailable_variants: string[];
  price?: string | null;
  base_price_ils?: string;
  base_price_usd?: string | null;
  original_price?: string | null;
  original_currency?: string | null;
  price_review_required?: boolean;
  images?: ApiImage[];
};
export type ApiTrader = {
  id: string;
  username: string;
  name_ar: string;
  name_en: string;
  email: string;
  phone?: string;
  country?: string;
  city?: string;
  category_discounts?: {category_id: number; discount_percent: string}[];
  active: boolean;
  is_staff?: boolean;
  price_list: {id: string; name_ar: string; name_en: string; currency_code: string; currency_symbol: string};
};
export type ApiOrder = {
  number: string;
  date: string;
  status: string;
  trader_name_ar: string;
  note: string;
  currency_symbol: string;
  total: string;
  items: {product_id: number | null; option: string; qty: number; unit_price: string}[];
};
export type ApiInvoice = {id: string; trader_id: string; date: string; amount: string; file_url: string; file_name: string};
export type ApiPriceList = {
  id: string;
  name_ar: string;
  name_en: string;
  currency_code: string;
  currency_symbol: string;
  pricing_mode?: "legacy" | "rule_based";
  default_discount_percent?: string;
  discount_scope?: "all" | "categories";
  scope_category_ids?: number[];
  is_default?: boolean;
  is_active?: boolean;
  prices: {product_id: number; price: string | null}[];
  category_rules?: {id: number; category_id: number; discount_percent: string; is_active: boolean}[];
  product_rules?: {id: number; product_id: number; discount_percent: string; is_active: boolean}[];
  quotes?: {product_id: number; base_price: string | null; base_currency: string; exchange_rate?: string | null; discount_percent: string | null; rule_source: string; category_id: number | null; calculated_price?: string | null; overridden?: boolean; price: string | null; currency_code: string; available: boolean; error: string}[];
};
export type ApiCurrency = {code: string; name: string; symbol: string};
export type UiCategory = {id?: number; ar: string; en: string; img?: string; parentId?: number | null; level?: number};
export type UiTrader = {id: string; ar: string; en: string; username: string; email: string; phone: string; country: string; city: string; list: string; active: boolean; admin: boolean; discounts: {category_id: number; discount_percent: string}[]};
export type UiCurrency = {id: string; name: string; symbol: string};
export type UiInvoice = {id: string; date: string; merchant: string; amount: number; url: string; name: string};

const ALL_CATEGORY: UiCategory = {ar: "جميع المنتجات", en: "All products"};

export function categoriesFromApi(rows: ApiCategory[]): UiCategory[] {
  const nodes = rows.map(row => ({
    id: row.id,
    ar: row.name_ar,
    en: row.name_en,
    img: resolveMedia(row.image),
    parentId: row.parent_id ?? null,
  }));
  const ordered: UiCategory[] = [];
  const walk = (parentId: number | null, level: number) => {
    nodes
      .filter(node => (node.parentId ?? null) === parentId)
      .sort((a, b) => a.id - b.id)
      .forEach(node => {
        ordered.push({...node, level});
        if (level < 3) walk(node.id, level + 1);
      });
  };
  walk(null, 1);
  nodes.filter(node => !ordered.some(item => item.id === node.id)).forEach(node => ordered.push({...node, level: 1}));
  return [ALL_CATEGORY, ...ordered];
}

export function productFromApi(row: ApiProduct, categories: UiCategory[], useBasePrice: boolean): Product {
  const categoryIndex = categories.findIndex(category => category.id === row.category_id);
  const source = useBasePrice ? row.base_price_ils : row.price;
  const main = resolveMedia(row.image);
  return {
    id: row.id,
    ar: row.name_ar,
    en: row.name_en,
    code: row.code,
    cat: categoryIndex > 0 ? categoryIndex : 1,
    price: source == null || source === "" ? Number.NaN : Number(source),
    sellingPrice: row.price == null || row.price === "" ? Number.NaN : Number(row.price),
    usdPrice: row.base_price_usd == null || row.base_price_usd === "" ? null : Number(row.base_price_usd),
    originalCurrency: row.original_currency === "CNY" || row.original_currency === "USD" || row.original_currency === "ILS" ? row.original_currency : undefined,
    originalPrice: row.original_price == null || row.original_price === "" ? null : Number(row.original_price),
    priceReview: !!row.price_review_required,
    unit: row.unit_ar,
    unitEn: row.unit_en,
    min: row.min_qty,
    available: row.available,
    isArchived: !!row.is_archived,
    image: main,
    gallery: (row.gallery || []).map(resolveMedia).filter(src => src && src !== main),
    badge: row.badge || undefined,
    desc: row.description_ar,
    descEn: row.description_en,
    options: row.options || [],
    colors: (row.colors || []).map(color => ({
      ar: color.name_ar,
      en: color.name_en,
      hex: color.hex,
      image: color.image ? resolveMedia(color.image) : undefined,
    })),
    sizes: row.sizes || [],
    unavailableVariants: row.unavailable_variants || [],
  };
}

export function rememberProduct(row: ApiProduct) {
  if (row.images) productImages.set(row.id, row.images);
  productColors.set(row.id, row.colors || []);
}

const productImages = new Map<number, ApiImage[]>();
const productColors = new Map<number, ApiColor[]>();

export function productsFromApi(rows: ApiProduct[], categories: UiCategory[], useBasePrice: boolean) {
  rows.forEach(rememberProduct);
  return rows.map(row => productFromApi(row, categories, useBasePrice));
}

export function traderFromApi(trader: ApiTrader): UiTrader {
  return {
    id: trader.id,
    ar: trader.name_ar,
    en: trader.name_en,
    username: trader.username,
    email: trader.email,
    phone: trader.phone || "",
    country: trader.country || "",
    city: trader.city || "",
    list: trader.price_list.id,
    active: trader.active,
    admin: trader.is_staff === true,
    discounts: trader.category_discounts || [],
  };
}

export function priceListFromApi(row: ApiPriceList): PriceList {
  return {
    id: row.id,
    ar: row.name_ar,
    en: row.name_en,
    currency: row.currency_code,
    prices: Object.fromEntries(row.prices.filter(item => item.price != null).map(item => [item.product_id, Number(item.price)])),
    mode: row.pricing_mode || "legacy",
    defaultDiscount: row.default_discount_percent || "0.00",
    discountScope: row.discount_scope || "all",
    scopeCategoryIds: row.scope_category_ids || [],
    isDefault: !!row.is_default,
    active: row.is_active !== false,
    categoryRules: (row.category_rules || []).map(rule => ({id: rule.id, categoryId: rule.category_id, discount: rule.discount_percent, active: rule.is_active})),
    productRules: (row.product_rules || []).map(rule => ({id: rule.id, productId: rule.product_id, discount: rule.discount_percent, active: rule.is_active})),
    quotes: (row.quotes || []).map(quote => ({
      productId: quote.product_id,
      basePrice: quote.base_price,
      baseCurrency: quote.base_currency,
      discount: quote.discount_percent,
      source: quote.rule_source,
      categoryId: quote.category_id,
      price: quote.price,
      calculated: quote.calculated_price ?? null,
      overridden: !!quote.overridden,
      currency: quote.currency_code,
      available: quote.available,
      error: quote.error,
    })),
  };
}

export function orderFromApi(row: ApiOrder): Order {
  const items: CartLine[] = row.items.map(item => ({
    key: `${item.product_id}-${item.option}`,
    id: item.product_id || 0,
    qty: item.qty,
    option: item.option,
    price: Number(item.unit_price),
  }));
  return {
    id: row.number,
    date: row.date,
    status: row.status,
    items,
    total: Number(row.total),
    currency: row.currency_symbol,
    note: row.note,
    merchant: row.trader_name_ar,
  };
}

export function invoiceFromApi(row: ApiInvoice): UiInvoice {
  return {
    id: row.id,
    date: row.date,
    merchant: row.trader_id,
    amount: Number(row.amount),
    url: resolveMedia(row.file_url),
    name: row.file_name,
  };
}

export function currencyFromApi(row: ApiCurrency): UiCurrency {
  return {id: row.code, name: row.name, symbol: row.symbol};
}

export function productWriteBody(product: Product, categoryId: number) {
  const currency = product.originalCurrency || "CNY";
  const original = typeof product.originalPrice === "number" && Number.isFinite(product.originalPrice) ? product.originalPrice.toFixed(2) : "0.00";
  return {
    name_ar: product.ar,
    name_en: product.en,
    code: product.code,
    category_id: categoryId,
    original_price: original,
    original_currency: currency,
    base_price_ils: currency === "ILS" ? original : (Number.isFinite(product.price) ? product.price.toFixed(2) : "0.00"),
    base_price_usd: currency === "USD" ? original : (product.usdPrice == null || !Number.isFinite(product.usdPrice) ? null : product.usdPrice.toFixed(2)),
    unit_ar: product.unit,
    unit_en: product.unitEn,
    min_qty: product.min,
    available: product.available,
    description_ar: product.desc || "",
    description_en: product.descEn || "",
    badge: product.badge || "",
    colors: (product.colors || []).map(color => ({name_ar: color.ar, name_en: color.en, hex: color.hex})),
    sizes: product.sizes || [],
    options: product.options,
    unavailable_variants: product.unavailableVariants || [],
  };
}

export async function syncProductMedia(productId: number, product: Product) {
  const wanted = [product.image, ...(product.gallery || [])].filter(Boolean);
  const existing = productImages.get(productId) || [];
  for (const image of existing) {
    const shown = resolveMedia(image.url || image.image_key);
    if (!wanted.includes(shown)) {
      await api(`/api/admin/products/${productId}/images/${image.id}/`, {method: "DELETE"});
    }
  }
  for (const [index, src] of wanted.entries()) {
    if (!src.startsWith("blob:")) continue;
    const body = new FormData();
    body.set("file", await fileFromBlob(src, `product-${productId}-${index}`));
    body.set("is_primary", String(src === product.image));
    body.set("sort_order", String(index));
    await api(`/api/admin/products/${productId}/images/`, {method: "POST", body});
  }
  const cover = existing.find(image => resolveMedia(image.url || image.image_key) === product.image);
  if (cover && !cover.is_primary && !product.image.startsWith("blob:")) {
    await api(`/api/admin/products/${productId}/images/${cover.id}/`, {
      method: "PATCH",
      body: JSON.stringify({is_primary: true}),
    });
  }
  const detail = await api<ApiProduct>(`/api/admin/products/${productId}/`);
  if (!detail.ok) return;
  for (const color of product.colors || []) {
    if (!color.image?.startsWith("blob:")) continue;
    const match = detail.data.colors.find(item => item.name_ar === color.ar && item.name_en === color.en);
    if (!match?.id) continue;
    const body = new FormData();
    body.set("file", await fileFromBlob(color.image, `color-${match.id}`));
    await api(`/api/admin/products/${productId}/colors/${match.id}/image/`, {method: "POST", body});
  }
}
