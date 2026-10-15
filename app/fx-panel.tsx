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

type HistoryRow = {date: string; usd_cny: string; usd_ils: string; provider: string; fetched_at: string};
type HistoryPage = {count: number; page: number; page_size: number; pages: number; from: string; to: string; results: HistoryRow[]};

const START = '2026-01-01';

export default function FxPanel({en}: {en: boolean}) {
  const t = (ar: string, english: string) => en ? english : ar;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<HistoryPage | null>(null);
  const [historyError, setHistoryError] = useState('');
  const [page, setPage] = useState(1);
  const [exact, setExact] = useState('');
  const [from, setFrom] = useState(START);
  const [to, setTo] = useState('');
  const [filterError, setFilterError] = useState('');
  const formatDate = (value?: string | null) => {
    if (!value) return t('غير متوفر', 'Not available');
    const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleDateString(en ? 'en-GB' : 'ar', {year: 'numeric', month: 'short', day: 'numeric'});
  };
  const formatStamp = (value?: string | null) => value ? new Date(value).toLocaleString(en ? 'en-GB' : 'ar') : t('غير متوفر', 'Not available');
  const loadSnapshot = async () => {
    const result = await api<Snapshot>('/api/admin/fx/');
    if (result.ok) setSnapshot(result.data);
  };
  const loadHistory = async (nextPage = page, filters = {exact, from, to}) => {
    if (filters.from && filters.to && filters.from > filters.to) {
      setFilterError(t('تاريخ البداية بعد تاريخ النهاية', 'From date is after to date'));
      return;
    }
    setFilterError('');
    const params = new URLSearchParams({page: String(nextPage), from: filters.from || START});
    if (filters.to) params.set('to', filters.to);
    if (filters.exact) params.set('date', filters.exact);
    const result = await api<HistoryPage>(`/api/admin/fx/history/?${params.toString()}`);
    if (!result.ok) {
      setHistoryError(t('تعذر تحميل سجل أسعار الصرف', 'Could not load exchange-rate history'));
      return;
    }
    setHistoryError('');
    setHistory(result.data);
    setPage(result.data.page);
    if (!filters.to && result.data.to) setTo(result.data.to);
  };
  useEffect(() => {void loadSnapshot(); void loadHistory(1)}, []);
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
    await loadHistory(1);
  };
  const applyFilters = (next: {exact?: string; from?: string; to?: string}) => {
    const filters = {exact: next.exact ?? exact, from: next.from ?? from, to: next.to ?? to};
    setExact(filters.exact);
    setFrom(filters.from);
    setTo(filters.to);
    setPage(1);
    void loadHistory(1, filters);
  };
  const status = snapshot?.status || 'missing';
  const statusLabel = status === 'current'
    ? t('محدّثة', 'Current')
    : status === 'stale'
      ? t('قديمة — الكتالوج ما زال يُعرض', 'Stale — the catalog remains visible')
      : status === 'blocked'
        ? t('قديمة جدًا — إيقاف تسعير الطلبات الجديدة', 'Too old — new checkout pricing is paused')
        : t('لا توجد أسعار بعد', 'No rates yet');
  const count = history?.count || 0;
  const size = history?.page_size || 30;
  const startRow = count ? (page - 1) * size + 1 : 0;
  const endRow = count ? Math.min(page * size, count) : 0;
  return <section className="fx-panel">
    <div className="fx-panel-head">
      <div>
        <strong>{t('أسعار الصرف الحالية', 'Current exchange rates')}</strong>
        <p>{t('المصدر', 'Source')}: Frankfurter</p>
      </div>
      <Button className="btn primary" type="button" disabled={busy} onClick={() => void refresh()}><RefreshCw size={16}/>{busy ? t('جارٍ التحديث', 'Refreshing') : t('تحديث الآن', 'Refresh now')}</Button>
    </div>
    <div className="fx-rates">
      {(['USD', 'CNY', 'ILS'] as const).map(code => <div key={code}><span>USD → <bdi>{code}</bdi></span><strong><bdi>{snapshot?.rates?.[code] || '—'}</bdi></strong></div>)}
    </div>
    <dl className="fx-meta">
      <div><dt>{t('المصدر', 'Provider')}</dt><dd>Frankfurter</dd></div>
      <div><dt>{t('تاريخ السعر لدى المصدر', 'Provider rate date')}</dt><dd><bdi>{formatDate(snapshot?.provider_date)}</bdi></dd></div>
      <div><dt>{t('آخر مزامنة ناجحة', 'Last successful synchronization')}</dt><dd><bdi>{formatStamp(snapshot?.fetched_at)}</bdi></dd></div>
      <div><dt>{t('حالة المزامنة', 'Synchronization status')}</dt><dd className={'fx-status ' + status}>{statusLabel}</dd></div>
    </dl>
    {error && <p className="product-editor-error" role="alert">{error}</p>}
    <div className="fx-history">
      <h3>{t('سجل أسعار الصرف', 'Exchange rate history')}</h3>
      <div className="fx-filters">
        <label>{t('التاريخ', 'Date')}<input type="date" value={exact} onChange={event => applyFilters({exact: event.target.value})}/></label>
        <label>{t('من تاريخ', 'From date')}<input type="date" value={from} onChange={event => applyFilters({from: event.target.value})}/></label>
        <label>{t('إلى تاريخ', 'To date')}<input type="date" value={to} onChange={event => applyFilters({to: event.target.value})}/></label>
        <button type="button" className="text-button" onClick={() => applyFilters({exact: '', from: START, to: ''})}>{t('إعادة ضبط', 'Reset')}</button>
      </div>
      {filterError && <p className="product-editor-error" role="alert">{filterError}</p>}
      {historyError && <p className="product-editor-error" role="alert">{historyError}</p>}
      {!historyError && history && !history.results.length && <p className="trader-discounts-empty">{t('لا توجد أسعار منشورة في هذا النطاق.', 'No published rates match this range.')}</p>}
      {!!history?.results.length && <div className="table-box fx-history-table">
        <table>
          <thead><tr>
            <th>{t('التاريخ', 'Date')}</th>
            <th>USD → CNY</th>
            <th>USD → ILS</th>
            <th>{t('المصدر', 'Provider')}</th>
            <th>{t('آخر جلب', 'Last fetched')}</th>
          </tr></thead>
          <tbody>
            {history.results.map(row => <tr key={row.date}>
              <td><bdi>{formatDate(row.date)}</bdi></td>
              <td><bdi>{row.usd_cny}</bdi></td>
              <td><bdi>{row.usd_ils}</bdi></td>
              <td>{row.provider}</td>
              <td><bdi>{formatDate(row.fetched_at)}</bdi></td>
            </tr>)}
          </tbody>
        </table>
      </div>}
      <div className="fx-pager">
        <span>{count ? t(`عرض ${startRow}–${endRow} من ${count}`, `Showing ${startRow}–${endRow} of ${count}`) : t('لا سجلات', 'No records')}</span>
        <div>
          <button type="button" className="btn light" disabled={page <= 1} onClick={() => void loadHistory(page - 1)}>{t('السابق', 'Previous')}</button>
          <bdi>{t(`صفحة ${page} من ${history?.pages || 0}`, `Page ${page} of ${history?.pages || 0}`)}</bdi>
          <button type="button" className="btn light" disabled={!history?.pages || page >= history.pages} onClick={() => void loadHistory(page + 1)}>{t('التالي', 'Next')}</button>
        </div>
      </div>
    </div>
  </section>;
}
