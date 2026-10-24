'use client';
import {useEffect, useMemo, useState} from 'react';
import {ArrowLeft, ArrowRight} from 'lucide-react';
import {toast} from 'sonner';
import {Button} from '@/components/ui/button';
import {Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle} from '@/components/ui/dialog';
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
  onAccessChanged: (result: {self: boolean; is_staff: boolean}) => Promise<void> | void;
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

export default function TraderForm({en, traderId, traders, categories, priceLists, loading, onDirty, onSaved, onAccessChanged, onCancel}: Props) {
  const t = (ar: string, english: string) => en ? english : ar;
  const creating = traderId === 'new';
  const trader = creating ? null : traders.find(item => item.id === traderId);
  const defaultList = priceLists.find(list => list.isDefault)?.id || priceLists[0]?.id || '';
  const [baseline, setBaseline] = useState(() => JSON.stringify(creating ? emptyDraft(defaultList) : trader ? fromTrader(trader) : null));
  const [draft, setDraft] = useState<Draft | null>(() => creating ? emptyDraft(defaultList) : trader ? fromTrader(trader) : null);
  const [busy, setBusy] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [accessBusy, setAccessBusy] = useState(false);
  const [accessError, setAccessError] = useState('');
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
  const confirmAccess = async () => {
    if (!trader || accessBusy) return;
    const granting = !trader.admin;
    setAccessBusy(true);
    setAccessError('');
    const result = await api<{is_staff: boolean; self: boolean; code?: string}>(`/api/admin/traders/${trader.id}/${granting ? 'promote' : 'revoke'}/`, {method: 'POST'});
    if (!result.ok) {
      setAccessBusy(false);
      const code = typeof result.data === 'object' && result.data && 'code' in result.data ? String(result.data.code) : '';
      if (code === 'last_admin') {
        setAccessError(t(
          'لا يمكن إلغاء صلاحيات آخر مدير نشط في النظام. يجب وجود مدير واحد على الأقل.',
          'Cannot revoke the last active administrator. At least one active administrator must remain.',
        ));
        return;
      }
      setAccessError(apiError(result.data, t('تعذر تحديث صلاحيات الحساب', 'Could not update account access')));
      return;
    }
    setAccessOpen(false);
    setAccessBusy(false);
    toast.success(granting ? t('تم تعيين المدير', 'Administrator assigned') : t('تم إلغاء صلاحيات المدير', 'Administrator access revoked'));
    await onAccessChanged({self: result.data.self, is_staff: result.data.is_staff});
  };
  const accessCopy = trader?.admin
    ? {
        title: t('تأكيد إلغاء صلاحيات المدير', 'Confirm Administrator Access Removal'),
        message: t(
          'هل أنت متأكد من إلغاء صلاحيات الإدارة لهذا المستخدم؟\n\nسيفقد إمكانية الوصول إلى لوحة الإدارة، وسيعود حسابه إلى صلاحيات التاجر العادي، مع الاحتفاظ ببياناته وطلباته ومعلومات حسابه.',
          "Are you sure you want to revoke this user's administrator access?\n\nThe account will lose access to the administration dashboard and return to normal trader permissions. Existing account data and order history will be preserved.",
        ),
        confirm: t('تأكيد إلغاء الصلاحيات', 'Revoke Access'),
      }
    : {
        title: t('تأكيد تعيين مدير', 'Confirm Administrator Assignment'),
        message: t(
          'هل أنت متأكد من تعيين هذا المستخدم كمدير للنظام؟\n\nسيحصل على صلاحيات كاملة للوصول إلى لوحة الإدارة، بما في ذلك إدارة المنتجات والتصنيفات والتجار والطلبات وقوائم الأسعار وإعدادات المتجر، بالإضافة إلى تعيين المديرين وإلغاء صلاحياتهم.',
          'Are you sure you want to make this user a system administrator?\n\nThis will grant full access to the administration dashboard, including product, category, trader, order, pricing and store management, as well as the ability to appoint and remove other administrators.',
        ),
        confirm: t('تأكيد التعيين', 'Confirm Assignment'),
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
    {trader && <section className="trader-form-section trader-access">
      <h3>{t('صلاحيات الحساب', 'Account Access')}</h3>
      <div className="trader-access-grid">
        <div className="trader-access-card"><small>{t('نوع الحساب', 'Account Type')}</small><strong>{trader.admin ? t('مدير النظام', 'Administrator') : t('تاجر', 'Trader')}</strong></div>
        <div className="trader-access-card"><small>{t('الوصول', 'Access')}</small><strong>{trader.admin ? t('إدارة كاملة', 'Full Administration') : t('تاجر عادي', 'Standard Trader')}</strong></div>
      </div>
      <p className="trader-access-note">{trader.admin
        ? t('يلغي هذا الإجراء صلاحيات الإدارة بعد التأكيد، ويعيد الحساب إلى تاجر عادي مع الاحتفاظ ببياناته وطلباته.', 'After confirmation, this removes administration access and returns the account to a standard trader. Account data and orders stay in place.')
        : t('يمنح هذا الإجراء صلاحيات الإدارة الكاملة بعد التأكيد، بما في ذلك تعيين المديرين وإلغاء صلاحياتهم.', 'After confirmation, this grants full administration access, including appointing and removing other administrators.')}</p>
      <div className="trader-form-actions">
        <Button type="button" className={trader.admin ? 'btn light' : 'btn primary'} disabled={busy || accessBusy} onClick={() => {setAccessError(''); setAccessOpen(true);}}>
          {trader.admin ? t('إلغاء صلاحيات المدير', 'Revoke Admin Access') : t('تعيين كمدير', 'Make Admin')}
        </Button>
      </div>
    </section>}
    <TraderDiscounts en={en} categories={categories} rows={draft.discounts} onChange={discounts => update({discounts})}/>
    <Dialog open={accessOpen} onOpenChange={next => {if (accessBusy) return; setAccessOpen(next); if (!next) setAccessError('');}}>
      <DialogContent dir={en ? 'ltr' : 'rtl'} className="access-dialog" showCloseButton>
        <DialogHeader style={{textAlign: 'start'}}>
          <DialogTitle>{accessCopy.title}</DialogTitle>
          <DialogDescription className="access-message">{accessCopy.message}</DialogDescription>
        </DialogHeader>
        {trader && <p className="access-identity"><strong>{en ? trader.en : trader.ar}</strong><bdi dir="ltr">{trader.email || trader.username}</bdi></p>}
        {accessError && <p className="access-error" role="alert">{accessError}</p>}
        <div className="access-dialog-actions">
          <Button type="button" className="btn light" disabled={accessBusy} onClick={() => {if (!accessBusy) {setAccessOpen(false); setAccessError('');}}}>{t('إلغاء', 'Cancel')}</Button>
          <Button type="button" className="btn primary" disabled={accessBusy} onClick={() => void confirmAccess()}>{accessBusy ? t('جارٍ التنفيذ', 'Working') : accessCopy.confirm}</Button>
        </div>
      </DialogContent>
    </Dialog>
  </form>;
}
