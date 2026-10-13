'use client';
import {Plus, Trash2} from 'lucide-react';
import CategoryPicker from './category-picker';

export type DiscountDraft = {category_id: number | null; discount_percent: string};

type Category = {id?: number; ar: string; en: string; parentId?: number | null; level?: number};

type Props = {
  en: boolean;
  categories: Category[];
  rows: DiscountDraft[];
  onChange: (rows: DiscountDraft[]) => void;
};

export default function TraderDiscounts({en, categories, rows, onChange}: Props) {
  const t = (ar: string, english: string) => en ? english : ar;
  const options = categories.filter(category => category.id).map(category => ({
    id: category.id as number,
    ar: category.ar,
    en: category.en,
    parentId: category.parentId ?? null,
    level: category.level,
  }));
  const update = (index: number, patch: Partial<DiscountDraft>) => {
    onChange(rows.map((row, rowIndex) => rowIndex === index ? {...row, ...patch} : row));
  };
  return <section className="trader-discounts">
    <div className="trader-discounts-head">
      <strong>{t('خصومات التصنيفات', 'Category discounts')}</strong>
      <button type="button" className="text-button" onClick={() => onChange([...rows, {category_id: null, discount_percent: '0'}])}>
        <Plus size={16}/>{t('إضافة خصم', 'Add a discount')}
      </button>
    </div>
    <p className="small muted">{t('يُطبَّق الخصم الأخص على منتجات التصنيف وتفرعاته. لا تُجمع الخصومات.', 'The most specific category discount applies to that category and its descendants. Discounts are not added together.')}</p>
    {!rows.length && <p className="trader-discounts-empty">{t('لا توجد خصومات خاصة لهذا التاجر. المنتجات تستخدم سعر القائمة.', 'This trader has no custom discounts. Products use the price-list price.')}</p>}
    <div className="trader-discount-list">
      {rows.map((row, index) => <div className="trader-discount-row" key={index}>
        <CategoryPicker
          en={en}
          label={t('التصنيف', 'Category')}
          categories={options}
          value={row.category_id}
          onChange={id => update(index, {category_id: id})}
          disabledReason={category => rows.some((item, itemIndex) => itemIndex !== index && item.category_id === category.id) ? t('هذا التصنيف مضاف بالفعل', 'This category is already added') : null}
        />
        <label className="field-label">{t('الخصم %', 'Discount %')}
          <input inputMode="decimal" dir="ltr" min="0" max="100" step="0.01" value={row.discount_percent} onChange={event => update(index, {discount_percent: event.target.value})}/>
        </label>
        <button type="button" className="icon-button" aria-label={t('حذف الخصم', 'Remove discount')} onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}><Trash2 size={16}/></button>
      </div>)}
    </div>
  </section>;
}
