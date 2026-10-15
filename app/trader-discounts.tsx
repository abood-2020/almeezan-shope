'use client';
import {useState} from 'react';
import {Plus, Trash2} from 'lucide-react';
import CategoryPicker, {CategoryTrail} from './category-picker';

export type DiscountDraft = {category_id: number | null; discount_percent: string};

type Category = {id?: number; ar: string; en: string; parentId?: number | null; level?: number};

type Props = {
  en: boolean;
  categories: Category[];
  rows: DiscountDraft[];
  onChange: (rows: DiscountDraft[]) => void;
};

function categoryNames(categories: Category[], id: number, en: boolean) {
  const names: string[] = [];
  const seen = new Set<number>();
  let current = categories.find(category => category.id === id);
  while (current?.id && !seen.has(current.id)) {
    seen.add(current.id);
    names.unshift(en ? current.en : current.ar);
    current = categories.find(category => category.id === current?.parentId);
  }
  return names;
}

export default function TraderDiscounts({en, categories, rows, onChange}: Props) {
  const t = (ar: string, english: string) => en ? english : ar;
  const options = categories.filter(category => category.id).map(category => ({
    id: category.id as number,
    ar: category.ar,
    en: category.en,
    parentId: category.parentId ?? null,
    level: category.level,
  }));
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [percent, setPercent] = useState('0');
  const [editing, setEditing] = useState<number | null>(null);
  const [draftPercent, setDraftPercent] = useState('');
  const [message, setMessage] = useState('');
  const validPercent = (value: string) => {
    const amount = Number(value);
    return Number.isFinite(amount) && amount >= 0 && amount <= 100;
  };
  const add = () => {
    if (!categoryId) {
      setMessage(t('اختر تصنيفًا', 'Choose a category'));
      return;
    }
    if (rows.some(row => row.category_id === categoryId)) {
      setMessage(t('هذا التصنيف مضاف بالفعل', 'This category is already added'));
      return;
    }
    if (!validPercent(percent)) {
      setMessage(t('نسبة الخصم يجب أن تكون بين 0 و 100', 'Discount must be between 0 and 100'));
      return;
    }
    onChange([...rows, {category_id: categoryId, discount_percent: Number(percent).toFixed(2)}]);
    setCategoryId(null);
    setPercent('0');
    setMessage('');
  };
  const saveEdit = (id: number) => {
    if (!validPercent(draftPercent)) {
      setMessage(t('نسبة الخصم يجب أن تكون بين 0 و 100', 'Discount must be between 0 and 100'));
      return;
    }
    onChange(rows.map(row => row.category_id === id ? {...row, discount_percent: Number(draftPercent).toFixed(2)} : row));
    setEditing(null);
    setMessage('');
  };
  const remove = (id: number) => {
    const name = categoryNames(categories, id, en).join(' / ');
    if (!window.confirm(t(`حذف خصم «${name}»؟`, `Remove the discount for “${name}”?`))) return;
    onChange(rows.filter(row => row.category_id !== id));
    if (editing === id) setEditing(null);
  };
  return <section className="trader-discounts trader-discount-table">
    <div className="trader-discounts-head">
      <strong>{t('خصومات التصنيفات', 'Category discounts')}</strong>
    </div>
    <p className="small muted">{t('هذه الخصومات تخص هذا التاجر فقط. يُطبَّق الخصم الأخص على التصنيف وتفرعاته، ولا تُجمع الخصومات ولا تُغيّر قائمة الأسعار المشتركة.', 'These discounts belong to this trader only. The most specific category rule applies to that category and its descendants. Discounts are not combined and do not change the shared price list.')}</p>
    <div className="discount-add">
      <CategoryPicker
        en={en}
        trail
        label={t('التصنيف', 'Category')}
        categories={options}
        value={categoryId}
        onChange={id => {setCategoryId(id); setMessage('');}}
        disabledReason={category => rows.some(row => row.category_id === category.id) ? t('هذا التصنيف مضاف بالفعل', 'This category is already added') : null}
      />
      <label className="field-label">{t('الخصم %', 'Discount %')}
        <input inputMode="decimal" dir="ltr" min="0" max="100" step="0.01" value={percent} onChange={event => setPercent(event.target.value)}/>
      </label>
      <button type="button" className="btn primary discount-add-button" onClick={add}><Plus size={16}/>{t('إضافة خصم', 'Add discount')}</button>
    </div>
    {message && <p className="discount-message" role="alert">{message}</p>}
    {!rows.length && <p className="trader-discounts-empty">{t('لا توجد خصومات خاصة لهذا التاجر. المنتجات تستخدم السعر الافتراضي.', 'This trader has no custom discounts. Products use the default price.')}</p>}
    {!!rows.length && <div className="table-box discount-rules">
      <table>
        <thead><tr>
          <th>{t('التصنيف', 'Category')}</th>
          <th>{t('الخصم %', 'Discount %')}</th>
          <th>{t('إجراءات', 'Actions')}</th>
        </tr></thead>
        <tbody>
          {rows.map(row => {
            const id = row.category_id || 0;
            const names = categoryNames(categories, id, en);
            return <tr key={id}>
              <td className="discount-category" data-label={t('التصنيف', 'Category')}>{names.length ? <CategoryTrail names={names} en={en}/> : <span className="cell-empty">—</span>}</td>
              <td className="discount-percent" data-label={t('الخصم %', 'Discount %')}>{editing === id
                ? <input dir="ltr" inputMode="decimal" min="0" max="100" step="0.01" value={draftPercent} onChange={event => setDraftPercent(event.target.value)} aria-label={t('نسبة الخصم', 'Discount percent')}/>
                : <bdi className="discount-pill">{Number(row.discount_percent).toFixed(2)}%</bdi>}</td>
              <td className="discount-actions" data-label={t('إجراءات', 'Actions')}>
                {editing === id
                  ? <button type="button" className="text-button" onClick={() => saveEdit(id)}>{t('حفظ النسبة', 'Save percent')}</button>
                  : <button type="button" className="text-button" onClick={() => {setEditing(id); setDraftPercent(row.discount_percent); setMessage('');}}>{t('تعديل', 'Edit')}</button>}
                <button type="button" className="text-button" onClick={() => remove(id)}><Trash2 size={14}/>{t('حذف', 'Delete')}</button>
              </td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>}
  </section>;
}
