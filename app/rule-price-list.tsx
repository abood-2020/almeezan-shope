'use client';
import {useEffect, useMemo, useState} from 'react';
import {toast} from 'sonner';
import {Button} from '@/components/ui/button';
import {Table, TableBody, TableCell, TableHead, TableHeader, TableRow} from '@/components/ui/table';
import {apiError, type ApiResult} from './api';
import type {PriceList, PriceQuote} from './pricing';
import type {Product} from './data';

type Request = <T>(path: string, options?: RequestInit) => Promise<ApiResult<T>>;
type Category = {id?: number; ar: string; en: string; parentId?: number | null; level?: number};

type Props = {
  en: boolean;
  list: PriceList;
  categories: Category[];
  products: Product[];
  currencies: {id: string; symbol: string}[];
  traderCount: number;
  request: Request;
  onBack: () => void;
  onRefresh: () => Promise<void>;
};

const moneyOf = (value: string) => {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toFixed(2) : '';
};

export default function RulePriceList({en, list, categories, products, currencies, traderCount, request, onBack, onRefresh}: Props) {
  const t = (ar: string, english: string) => en ? english : ar;
  const symbol = currencies.find(currency => currency.id === list.currency)?.symbol || list.currency;
  const signature = `${list.id}|${list.defaultDiscount}|${list.discountScope}|${(list.scopeCategoryIds || []).join(',')}|${(list.quotes || []).map(quote => `${quote.productId}:${quote.price}:${quote.calculated}:${quote.overridden}`).join(';')}`;
  const [discount, setDiscount] = useState(list.defaultDiscount || '0.00');
  const [scope, setScope] = useState<'all' | 'categories'>(list.discountScope || 'all');
  const [scopeIds, setScopeIds] = useState<number[]>(list.scopeCategoryIds || []);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [query, setQuery] = useState('');
  const [categoryId, setCategoryId] = useState('all');
  const [view, setView] = useState<'all' | 'discount' | 'outside' | 'override' | 'missing'>('all');
  const [page, setPage] = useState(1);
  useEffect(() => {
    setDiscount(list.defaultDiscount || '0.00');
    setScope(list.discountScope === 'categories' ? 'categories' : 'all');
    setScopeIds(list.scopeCategoryIds || []);
    setDrafts({});
  }, [signature, list.defaultDiscount, list.discountScope, list.scopeCategoryIds]);
  const quotes = useMemo(() => new Map((list.quotes || []).map(quote => [quote.productId, quote])), [list.quotes]);
  const categoryName = (product: Product) => {
    const category = categories[product.cat];
    return category ? (en ? category.en : category.ar) : '';
  };
  const inCategory = (product: Product) => {
    if (categoryId === 'all') return true;
    const selected = Number(categoryId);
    let current = categories[product.cat];
    const seen = new Set<number>();
    while (current?.id && !seen.has(current.id)) {
      if (current.id === selected) return true;
      seen.add(current.id);
      current = categories.find(category => category.id === current?.parentId);
    }
    return false;
  };
  const shown = (product: Product, quote?: PriceQuote) => drafts[product.id] ?? (quote?.overridden && quote.price != null ? quote.price : quote?.calculated ?? '');
  const rows = products.map(product => ({product, quote: quotes.get(product.id)})).filter(({product, quote}) => {
    const haystack = `${product.ar} ${product.en} ${product.code}`.toLowerCase();
    if (query && !haystack.includes(query.toLowerCase())) return false;
    if (!inCategory(product)) return false;
    if (view === 'discount') return quote?.source === 'discount';
    if (view === 'outside') return quote?.source === 'base';
    if (view === 'override') return drafts[product.id] != null ? moneyOf(drafts[product.id]) !== (quote?.calculated ?? '') && drafts[product.id].trim() !== '' : !!quote?.overridden;
    if (view === 'missing') return !quote?.available && !quote?.overridden;
    return true;
  });
  const pages = Math.max(1, Math.ceil(rows.length / 10));
  const currentPage = Math.min(page, pages);
  const visible = rows.slice((currentPage - 1) * 10, currentPage * 10);
  const toggleCategory = (id: number) => setScopeIds(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  const save = async () => {
    const discountNumber = Number(discount);
    if (!Number.isFinite(discountNumber) || discountNumber < 0 || discountNumber > 100) {
      toast.error(t('نسبة الخصم يجب أن تكون بين 0 و 100', 'Discount must be between 0 and 100'));
      return;
    }
    const prices: {product_id: number; price: string}[] = [];
    for (const product of products) {
      const quote = quotes.get(product.id);
      const entered = shown(product, quote).trim();
      const calculated = quote?.calculated ?? '';
      if (entered === '') continue;
      const normalized = moneyOf(entered);
      if (!normalized || Number(normalized) < 0) {
        toast.error(t('راجع الأسعار؛ استخدم أرقامًا موجبة أو صفرًا.', 'Check prices; use non-negative numbers.'));
        return;
      }
      if (normalized !== calculated) prices.push({product_id: product.id, price: normalized});
    }
    const settings = await request(`/api/admin/price-lists/${list.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({
        default_discount_percent: discountNumber.toFixed(2),
        discount_scope: scope,
        scope_category_ids: scope === 'categories' ? scopeIds : [],
        is_default: !!list.isDefault && discountNumber === 0,
      }),
    });
    if (!settings.ok) {toast.error(apiError(settings.data, t('تعذر حفظ القائمة', 'Could not save the list'))); return;}
    const saved = await request(`/api/admin/price-lists/${list.id}/prices/`, {method: 'PUT', body: JSON.stringify({prices})});
    if (!saved.ok) {toast.error(apiError(saved.data, t('تعذر حفظ أسعار القائمة', 'Could not save the price list'))); return;}
    await onRefresh();
    toast.success(t('تم حفظ أسعار القائمة', 'Price list saved'));
  };
  return <div className="pricing-workspace">
    <button className="text-button pricing-back" onClick={onBack}>{t('جميع قوائم الأسعار', 'All price lists')}</button>
    <div className="price-detail-header"><div><span className="eyebrow">{t('أسعار المنتجات', 'PRODUCT PRICES')}</span><h2>{en ? list.en : list.ar}</h2><p><bdi>{list.currency} · {symbol}</bdi><span>·</span>{traderCount} {t('تجار مرتبطون', 'assigned traders')}</p></div></div>
    <section className="pricing-rule-card price-settings">
      <h3>{t('الخصم ونطاقه', 'Discount and scope')}</h3>
      <p className="small muted">{t('يُحسب السعر تلقائيًا من السعر الأساسي بعملة القائمة. السعر اليدوي يبقى ثابتًا حتى تعيده.', 'The price is calculated from the base price in this list’s currency. A manual price stays fixed until you reset it.')}</p>
      <div className="price-settings-grid">
        <label>{t('نسبة الخصم العامة', 'Global discount %')}<input aria-label={t('نسبة الخصم العامة', 'Global discount')} inputMode="decimal" dir="ltr" value={discount} onChange={event => setDiscount(event.target.value)}/></label>
        <label className="check-label"><input type="checkbox" checked={!!list.isDefault} disabled={Number(discount) !== 0} onChange={event => void request(`/api/admin/price-lists/${list.id}/`, {method: 'PATCH', body: JSON.stringify({is_default: event.target.checked, default_discount_percent: '0'})}).then(async result => {if (!result.ok) toast.error(apiError(result.data, t('تعذر حفظ القائمة', 'Could not save the list'))); else await onRefresh();})}/>{t('افتراضية للتجار الجدد بخصم 0%', 'Default for future traders at 0%')}</label>
      </div>
      <div className="scope-choice" role="radiogroup" aria-label={t('نطاق الخصم', 'Discount scope')}>
        <label><input type="radio" name="discount-scope" checked={scope === 'all'} onChange={() => setScope('all')}/>{t('كل المنتجات', 'All products')}</label>
        <label><input type="radio" name="discount-scope" checked={scope === 'categories'} onChange={() => setScope('categories')}/>{t('تصنيفات محددة', 'Selected categories')}</label>
      </div>
      {scope === 'categories' && <div className="scope-list">{categories.filter(category => category.id).map(category => <label key={category.id} style={{paddingInlineStart: `${((category.level || 1) - 1) * 16}px`}}><input type="checkbox" checked={scopeIds.includes(category.id as number)} onChange={() => toggleCategory(category.id as number)}/>{en ? category.en : category.ar}</label>)}<p className="small muted">{t('اختيار تصنيف يشمل تصنيفاته الفرعية. المنتج خارج النطاق يبقى بسعره الأساسي.', 'Choosing a category includes its subcategories. A product outside the scope keeps its base price.')}</p></div>}
    </section>
    <div className="price-detail-panel">
      <div className="price-table-toolbar">
        <div className="inline-search"><input aria-label={t('بحث منتجات القائمة', 'Search products in list')} value={query} placeholder={t('ابحث باسم المنتج أو الكود…', 'Search by product name or code…')} onChange={event => {setQuery(event.target.value); setPage(1);}}/></div>
        <select className="choice" aria-label={t('تصنيف المنتجات', 'Product category')} value={categoryId} onChange={event => {setCategoryId(event.target.value); setPage(1);}}>
          <option value="all">{t('جميع التصنيفات', 'All categories')}</option>
          {categories.filter(category => category.id).map(category => <option key={category.id} value={String(category.id)}>{`${'— '.repeat(Math.max(0, (category.level || 1) - 1))}${en ? category.en : category.ar}`}</option>)}
        </select>
        <span className="small muted">{rows.length} {t('نتيجة', 'results')}</span>
      </div>
      <div className="price-status-filters" role="group" aria-label={t('حالة الأسعار', 'Price status')}>
        {([['all', t('كل المنتجات', 'All products')], ['discount', t('ضمن الخصم', 'Discounted')], ['outside', t('خارج النطاق', 'Outside scope')], ['override', t('سعر يدوي', 'Manual price')], ['missing', t('بدون سعر', 'Missing price')]] as const).map(([id, label]) => <button key={id} type="button" className={view === id ? 'active' : ''} aria-pressed={view === id} onClick={() => {setView(id); setPage(1);}}>{label}</button>)}
      </div>
      <div className="table-box price-editor-table"><Table><TableHeader><TableRow>
        <TableHead>{t('المنتج', 'Product')}</TableHead>
        <TableHead>{t('السعر الأساسي', 'Base price')}</TableHead>
        <TableHead>{t('الخصم', 'Discount')}</TableHead>
        <TableHead>{t('السعر المحسوب', 'Calculated')}</TableHead>
        <TableHead>{t('سعر القائمة', 'List price')}</TableHead>
        <TableHead>{t('الحالة', 'Status')}</TableHead>
      </TableRow></TableHeader><TableBody>{visible.map(({product, quote}) => {
        const value = shown(product, quote);
        const missing = !quote?.available && !quote?.overridden;
        const manual = quote?.overridden && (drafts[product.id] == null || moneyOf(drafts[product.id]) !== (quote.calculated ?? ''));
        return <TableRow key={product.id} className={quote?.source === 'discount' ? 'price-row-scoped' : ''}>
          <TableCell data-label={t('المنتج', 'Product')}><strong>{en ? product.en : product.ar}</strong><small className="block"><bdi>{product.code}</bdi> · {categoryName(product)}</small></TableCell>
          <TableCell data-label={t('السعر الأساسي', 'Base price')}>{quote?.basePrice == null ? <span className="missing-price">{t('لا يوجد سعر بهذه العملة', 'No price in this currency')}</span> : <bdi>{quote.basePrice} {symbol}</bdi>}</TableCell>
          <TableCell data-label={t('الخصم', 'Discount')}>{quote?.discount == null ? '—' : <bdi>{quote.discount}%</bdi>}</TableCell>
          <TableCell data-label={t('السعر المحسوب', 'Calculated')}>{quote?.calculated == null ? '—' : <bdi>{quote.calculated} {symbol}</bdi>}</TableCell>
          <TableCell data-label={t('سعر القائمة', 'List price')}><div className="editable-price"><input aria-label={`${en ? product.en : product.ar} — ${t('سعر القائمة', 'list price')}`} inputMode="decimal" dir="ltr" value={value} placeholder={missing ? t('غير محدد', 'Not set') : undefined} onChange={event => setDrafts(current => ({...current, [product.id]: event.target.value}))}/><span>{symbol}</span></div></TableCell>
          <TableCell data-label={t('الحالة', 'Status')}><span className={'status-pill' + (manual || quote?.source === 'discount' ? ' on' : '')}>{manual ? t('سعر يدوي', 'Manual') : missing ? t('غير متاح', 'Unavailable') : quote?.source === 'discount' ? t('ضمن الخصم', 'Discounted') : t('سعر أساسي', 'Base price')}</span>{(manual || quote?.calculated != null) && <button type="button" className="text-button" onClick={() => setDrafts(current => ({...current, [product.id]: quote?.calculated ?? ''}))}>{t('إعادة للحساب', 'Reset')}</button>}</TableCell>
        </TableRow>;
      })}</TableBody></Table></div>
      <div className="price-table-bottom"><span>{rows.length ? `${(currentPage - 1) * 10 + 1}–${Math.min(currentPage * 10, rows.length)}` : '0'} {t('من', 'of')} {rows.length}</span><div className="button-row"><Button className="btn light" disabled={currentPage === 1} onClick={() => setPage(current => current - 1)}>{t('السابق', 'Previous')}</Button><span className="page-number">{currentPage} / {pages}</span><Button className="btn light" disabled={currentPage === pages} onClick={() => setPage(current => current + 1)}>{t('التالي', 'Next')}</Button></div></div>
    </div>
    <div className="price-savebar"><div><strong>{t('الحفظ يعتمد الحساب في الخادم', 'Saving uses the server calculation')}</strong><small>{t('الأسعار المرسلة من الشاشة لا تُعتمد إلا كسعر نهائي يدوي.', 'A typed price is stored only as a manual final price.')}</small></div><Button className="btn primary" onClick={() => void save()}>{t('حفظ الأسعار', 'Save prices')}</Button></div>
  </div>;
}
