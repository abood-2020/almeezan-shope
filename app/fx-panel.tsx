'use client';
import {useEffect, useState} from 'react';
import {RefreshCw} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {api} from './api';

type Snapshot = {
  provider: string;
  provider_date: string | null;
  fetched_at: string | null;
  status: string;
  checkout_allowed: boolean;
  rates: Record<string, string>;
};

const symbols: Record<string, string> = {USD: '$', ILS: '₪', CNY: '¥'};

export default function FxPanel({en}: {en: boolean}) {
  const t = (ar: string, english: string) => en ? english : ar;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = async () => {
    const result = await api<Snapshot>('/api/admin/fx/');
    if (result.ok) setSnapshot(result.data);
  };
  useEffect(() => {void load()}, []);
  const refresh = async () => {
    setBusy(true);
    setError('');
    const result = await api<Snapshot & {error?: string}>('/api/admin/fx/refresh/', {method: 'POST'});
    setBusy(false);
    if (!result.ok) {
      if (result.data && typeof result.data === 'object' && 'rates' in result.data) setSnapshot(result.data as Snapshot);
      setError(t('تعذر تحديث الأسعار. بقيت آخر أسعار صحيحة.', 'The refresh failed. The last valid rates are still in use.'));
      return;
    }
    setSnapshot(result.data);
  };
  const status = snapshot?.status || 'missing';
  const statusLabel = status === 'current'
    ? t('محدّثة', 'Current')
    : status === 'stale'
      ? t('قديمة — الكتالوج ما زال يُعرض', 'Stale — the catalog remains visible')
      : status === 'blocked'
        ? t('قديمة جدًا — إيقاف تسعير الطلبات الجديدة', 'Too old — new checkout pricing is paused')
        : t('لا توجد أسعار بعد', 'No rates yet');
  const when = (value?: string | null) => value ? new Date(value).toLocaleString(en ? 'en-GB' : 'ar') : t('غير متوفر', 'Not available');
  return <section className="fx-panel">
    <div className="fx-panel-head">
      <div>
        <strong>{t('أسعار الصرف', 'Exchange rates')}</strong>
        <p>{t('المصدر', 'Source')}: Frankfurter · USD → CNY / ILS</p>
      </div>
      <Button className="btn primary" type="button" disabled={busy} onClick={() => void refresh()}><RefreshCw size={16}/>{busy ? t('جارٍ التحديث', 'Refreshing') : t('تحديث الآن', 'Refresh now')}</Button>
    </div>
    <div className="fx-rates">
      {(['USD', 'ILS', 'CNY'] as const).map(code => <div key={code}><span>{symbols[code]}</span><strong><bdi>{code}</bdi></strong><bdi>{snapshot?.rates?.[code] || '—'}</bdi><small>{t('لكل دولار', 'per USD')}</small></div>)}
    </div>
    <dl className="fx-meta">
      <div><dt>{t('حالة المزامنة', 'Synchronization')}</dt><dd className={'fx-status ' + status}>{statusLabel}</dd></div>
      <div><dt>{t('تاريخ السعر لدى المصدر', 'Provider rate date')}</dt><dd><bdi>{snapshot?.provider_date || t('غير متوفر', 'Not available')}</bdi></dd></div>
      <div><dt>{t('آخر تحديث ناجح', 'Last successful update')}</dt><dd><bdi>{when(snapshot?.fetched_at)}</bdi></dd></div>
    </dl>
    {error && <p className="product-editor-error" role="alert">{error}</p>}
  </section>;
}
