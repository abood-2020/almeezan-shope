'use client';
import {useEffect, useState} from 'react';
import {toast} from 'sonner';
import {Button} from '@/components/ui/button';
import {apiError, type ApiResult} from './api';

type Rate = {id: number; source: string; target: string; rate: string; is_active: boolean; updated_at: string};
type Request = <T>(path: string, options?: RequestInit) => Promise<ApiResult<T>>;

export default function ExchangeRateManager({en, currencies, request}: {en: boolean; currencies: {id: string; symbol: string}[]; request: Request}) {
  const t = (ar: string, english: string) => en ? english : ar;
  const [rates, setRates] = useState<Rate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [source, setSource] = useState(currencies[0]?.id || 'ILS');
  const [target, setTarget] = useState(currencies[1]?.id || currencies[0]?.id || 'USD');
  const [rate, setRate] = useState('');
  const load = async () => {
    const result = await request<Rate[]>('/api/admin/exchange-rates/');
    setLoading(false);
    if (!result.ok) {setError(t('تعذر تحميل أسعار الصرف', 'Could not load exchange rates')); return;}
    setError('');
    setRates(result.data);
  };
  useEffect(() => {void load();}, []);
  const preview = rate.trim() || '—';
  const save = async () => {
    const amount = Number(rate);
    if (source === target) {setFormError(t('اختر عملتين مختلفتين. الاتجاه العكسي لا يُستنتج تلقائيًا.', 'Choose two different currencies. A reverse rate is never assumed.')); return;}
    if (!rate.trim() || !Number.isFinite(amount) || amount <= 0) {setFormError(t('أدخل سعر صرف أكبر من صفر.', 'Enter an exchange rate greater than zero.')); return;}
    setFormError('');
    setSaving(true);
    const result = await request<Rate>('/api/admin/exchange-rates/', {method: 'POST', body: JSON.stringify({source, target, rate})});
    setSaving(false);
    if (!result.ok) {toast.error(apiError(result.data, t('تعذر حفظ سعر الصرف', 'Could not save the exchange rate'))); return;}
    setRate('');
    toast.success(t('تم حفظ سعر الصرف', 'Exchange rate saved'));
    await load();
  };
  return <section className="rates-card">
    <header className="rates-head">
      <h2>{t('أسعار صرف العملات', 'Currency Exchange Rates')}</h2>
      <p>{t('حدّد سعر التحويل يدويًا. 1 من عملة المصدر يساوي السعر بعملة الهدف، ولا يُفترض الاتجاه العكسي.', 'Set rates manually. 1 source unit equals the rate in the target currency. The reverse direction is never assumed.')}</p>
    </header>
    <p className="rate-formula" aria-live="polite"><bdi>1 {source} = {preview} {target}</bdi></p>
    {error && <p className="error-box" role="alert">{error}</p>}
    {formError && <p className="error-box" role="alert">{formError}</p>}
    <div className="rates-form">
      <label>{t('من عملة', 'Source currency')}<select aria-label={t('عملة المصدر', 'Source currency')} value={source} onChange={event => setSource(event.target.value)}>{currencies.map(currency => <option key={currency.id} value={currency.id}>{currency.id}</option>)}</select></label>
      <label>{t('إلى عملة', 'Target currency')}<select aria-label={t('عملة الهدف', 'Target currency')} value={target} onChange={event => setTarget(event.target.value)}>{currencies.map(currency => <option key={currency.id} value={currency.id}>{currency.id}</option>)}</select></label>
      <label>{t('سعر الصرف', 'Exchange rate')}<input aria-label={t('سعر الصرف', 'Exchange rate')} inputMode="decimal" dir="ltr" value={rate} placeholder="0.00" onChange={event => setRate(event.target.value)}/></label>
      <Button className="btn primary" disabled={saving} onClick={() => void save()}>{saving ? t('جارٍ الحفظ…', 'Saving…') : t('حفظ السعر', 'Save rate')}</Button>
    </div>
    {loading && <p className="small muted">{t('جارٍ تحميل أسعار الصرف…', 'Loading exchange rates…')}</p>}
    {!loading && !error && !!rates.length && <ul className="rates-list">
      {rates.map(item => <li key={item.id}>
        <div className="rate-pair"><strong><bdi>1 {item.source} = {item.rate} {item.target}</bdi></strong><small>{formatStamp(item.updated_at, en)}</small></div>
        <span className={'status-pill' + (item.is_active ? ' on' : '')}>{item.is_active ? t('مفعّل', 'Active') : t('متوقف', 'Inactive')}</span>
        <Button className="btn light" onClick={() => void request(`/api/admin/exchange-rates/${item.id}/`, {method: 'PATCH', body: JSON.stringify({is_active: !item.is_active})}).then(result => {if (!result.ok) toast.error(apiError(result.data, t('تعذر تحديث السعر', 'Could not update the rate'))); else void load();})}>{item.is_active ? t('إيقاف', 'Deactivate') : t('تفعيل', 'Activate')}</Button>
      </li>)}
    </ul>}
    {!loading && !error && !rates.length && <p className="small muted">{t('لا توجد أسعار صرف بعد.', 'No exchange rates yet.')}</p>}
  </section>;
}

function formatStamp(value: string, en: boolean) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(en ? 'en-GB' : 'ar', {dateStyle: 'medium', timeStyle: 'short'}).format(date);
}
