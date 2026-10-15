'use client';
import {useEffect, useMemo, useState} from 'react';
import {ArrowLeft, ArrowRight} from 'lucide-react';
import {toast} from 'sonner';
import {Button} from '@/components/ui/button';
import {api, apiError} from './api';
import TraderDiscounts, {type DiscountDraft} from './trader-discounts';
import type {UiTrader} from './adapt';

type Category = {id?: number; ar: string; en: string; parentId?: number | null; level?: number};
type PriceListOption = {id: string; ar: string; en: string; isDefault?: boolean};

type Draft = {
  ar: string;
  en: string;
  username: string;
  email: string;
  phone: string;
  country: string;
  city: string;
  list: string;
  active: boolean;
  discounts: DiscountDraft[];
};

type Props = {
  en: boolean;
  traderId: string;
  traders: UiTrader[];
  categories: Category[];
  priceLists: PriceListOption[];
  loading: boolean;
  onDirty: (dirty: boolean) => void;
  onSaved: (id: string) => Promise<void> | void;
  onCancel: () => void;
};

const emptyDraft = (list: string): Draft => ({
  ar: '', en: '', username: '', email: '', phone: '', country: '', city: '', list, active: true, discounts: [],
});

function fromTrader(trader: UiTrader): Draft {
  return {
    ar: trader.ar,
    en: trader.en,
    username: trader.username,
    email: trader.email,
    phone: trader.phone,
    country: trader.country,
    city: trader.city,
    list: trader.list,
    active: trader.active,
    discounts: (trader.discounts || []).map(row => ({category_id: row.category_id, discount_percent: row.discount_percent})),
  };
}

export default function TraderForm({en, traderId, traders, categories, priceLists, loading, onDirty, onSaved, onCancel}: Props) {
  const t = (ar: string, english: string) => en ? english : ar;
  const creating = traderId === 'new';
  const trader = creating ? null : traders.find(item => item.id === traderId);
  const defaultList = priceLists.find(list => list.isDefault)?.id || priceLists[0]?.id || '';
  const [baseline, setBaseline] = useState(() => JSON.stringify(creating ? emptyDraft(defaultList) : trader ? fromTrader(trader) : null));
  const [draft, setDraft] = useState<Draft | null>(() => creating ? emptyDraft(defaultList) : trader ? fromTrader(trader) : null);
  const [busy, setBusy] = useState(false);
  const snapshot = useMemo(() => draft ? JSON.stringify(draft) : '', [draft]);
  useEffect(() => {onDirty(!!draft && snapshot !== baseline)}, [baseline, draft, onDirty, snapshot]);
  useEffect(() => {
    if (!creating || !defaultList) return;
    setDraft(current => current && !current.list ? {...current, list: defaultList} : current);
    setBaseline(current => {
      if (!current) return current;
      const parsed = JSON.parse(current) as Draft | null;
      if (!parsed || parsed.list) return current;
      return JSON.stringify({...parsed, list: defaultList});
    });
  }, [creating, defaultList]);
  useEffect(() => {
    if (creating) return;
    if (!trader) return;
    const next = fromTrader(trader);
    const serialized = JSON.stringify(next);
    setDraft(current => {
      if (current && JSON.stringify(current) !== baseline) return current;
      return next;
    });
    setBaseline(serialized);
  }, [baseline, creating, trader]);
  if (loading && !creating && !trader) return <p className="muted">{t('جارٍ تحميل التاجر', 'Loading trader')}</p>;
  if (!creating && !trader) return <div className="trader-form-page"><button type="button" className="text-button" onClick={onCancel}>{t('العودة إلى التجار', 'Back to traders')}</button><p>{t('لم يتم العثور على هذا التاجر.', 'This trader could not be found.')}</p></div>;
  if (!draft) return null;
  const update = (patch: Partial<Draft>) => setDraft({...draft, ...patch});
  const save = async () => {
    if (traders.some(item => item.username === draft.username && item.id !== trader?.id)) {
      toast.error(t('اسم المستخدم مستخدم', 'Username already in use'));
      return;
    }
    const generated = String(draft.username).toLowerCase().replace(/[^\w-]/g, '').slice(0, 32);
    const id = trader?.id || generated;
    if (!id || !draft.ar.trim() || !draft.en.trim() || !draft.username.trim() || !draft.list) {
      toast.error(t('أكمل الاسم واسم المستخدم وقائمة الأسعار', 'Enter the name, username and price list'));
      return;
    }
    const discounts = draft.discounts.map(row => ({category_id: row.category_id, discount_percent: row.discount_percent}));
    if (discounts.some(row => !row.category_id)) {
      toast.error(t('اختر تصنيفًا لكل خصم', 'Choose a category for every discount'));
      return;
    }
    const seen = new Set<number>();
    if (discounts.some(row => {
      if (seen.has(row.category_id as number)) return true;
      seen.add(row.category_id as number);
      return false;
    })) {
      toast.error(t('لا يمكن تكرار خصم نفس التصنيف', 'A category cannot have two discounts'));
      return;
    }
    if (discounts.some(row => {
      const value = Number(row.discount_percent);
      return !Number.isFinite(value) || value < 0 || value > 100;
    })) {
      toast.error(t('نسبة الخصم يجب أن تكون بين 0 و 100', 'Discount must be between 0 and 100'));
      return;
    }
    const body = {
      name_ar: draft.ar.trim(),
      name_en: draft.en.trim(),
      username: draft.username.trim(),
      email: draft.email.trim(),
      phone: draft.phone.trim(),
      country: draft.country.trim(),
      city: draft.city.trim(),
      price_list_id: draft.list,
      active: draft.active,
      category_discounts: discounts,
    };
    setBusy(true);
    const result = await api(trader ? `/api/admin/traders/${trader.id}/` : '/api/admin/traders/', {
      method: trader ? 'PATCH' : 'POST',
      body: JSON.stringify(trader ? body : {...body, id}),
    });
    if (!result.ok) {
      setBusy(false);
      toast.error(apiError(result.data, t('تعذر حفظ التعديلات', 'Could not save the changes')));
      return;
    }
    if (!trader) {
      const passwordResult = await api(`/api/admin/traders/${id}/set-password/`, {method: 'POST', body: JSON.stringify({password: 'demo123'})});
      if (!passwordResult.ok) {
        setBusy(false);
        toast.error(apiError(passwordResult.data, t('تم إنشاء التاجر وتعذر تعيين كلمة المرور', 'The trader was created, but the password could not be set')));
        return;
      }
    }
    setBaseline(JSON.stringify(draft));
    setBusy(false);
    toast.success(t('تم حفظ التاجر', 'Trader saved'));
    await onSaved(id);
  };
  const Back = en ? ArrowLeft : ArrowRight;
  return <form className="trader-form-page" onSubmit={event => {event.preventDefault(); void save();}}>
    <header className="trader-form-header">
      <div>
        <button type="button" className="text-button" onClick={onCancel}><Back size={16}/>{t('العودة إلى التجار', 'Back to traders')}</button>
        <h2>{draft.ar || draft.en || t('تاجر جديد', 'New trader')}</h2>
        <span className={'status ' + (draft.active ? 'complete' : 'cancelled')}>{draft.active ? t('نشط', 'Active') : t('غير نشط', 'Inactive')}</span>
      </div>
      <div className="trader-form-actions">
        <Button type="button" className="btn light" onClick={onCancel}>{t('إلغاء', 'Cancel')}</Button>
        <Button type="submit" className="btn primary" disabled={busy}>{busy ? t('جارٍ الحفظ', 'Saving') : t('حفظ التعديلات', 'Save changes')}</Button>
      </div>
    </header>
    <section className="trader-form-section">
      <h3>{t('بيانات النشاط والحساب', 'Business and account')}</h3>
      <div className="trader-form-grid">
        <label className="field-label">{t('الاسم بالعربية', 'Arabic name')}<input required value={draft.ar} onChange={event => update({ar: event.target.value})}/></label>
        <label className="field-label">{t('الاسم بالإنجليزية', 'English name')}<input required dir="ltr" value={draft.en} onChange={event => update({en: event.target.value})}/></label>
        <label className="field-label">{t('اسم المستخدم', 'Username')}<input required dir="ltr" value={draft.username} onChange={event => update({username: event.target.value})}/></label>
        <label className="field-label">{t('البريد الإلكتروني', 'Email')}<input type="email" dir="ltr" value={draft.email} onChange={event => update({email: event.target.value})}/></label>
        <label className="field-label">{t('رقم الهاتف', 'Phone number')}<input dir="ltr" value={draft.phone} onChange={event => update({phone: event.target.value})}/></label>
        <label className="field-label">{t('الدولة', 'Country')}<input value={draft.country} onChange={event => update({country: event.target.value})}/></label>
        <label className="field-label">{t('المدينة', 'City')}<input value={draft.city} onChange={event => update({city: event.target.value})}/></label>
        <label className="field-label">{t('قائمة الأسعار', 'Price list')}<select required value={draft.list} onChange={event => update({list: event.target.value})}><option value="" disabled>{t('اختر قائمة', 'Choose a list')}</option>{priceLists.map(list => <option key={list.id} value={list.id}>{en ? list.en : list.ar}</option>)}</select></label>
        <label className="check-label trader-active"><input type="checkbox" checked={draft.active} onChange={event => update({active: event.target.checked})}/>{t('الحساب نشط', 'Account active')}</label>
      </div>
      {creating && <p className="small muted trader-password-note">{t('كلمة المرور الأولية:', 'Initial password:')} <bdi>demo123</bdi></p>}
    </section>
    <TraderDiscounts en={en} categories={categories} rows={draft.discounts} onChange={discounts => update({discounts})}/>
  </form>;
}
