'use client';
import {useMemo, useState} from 'react';
import {Download, Upload} from 'lucide-react';
import {toast} from 'sonner';
import {Button} from '@/components/ui/button';
import {Dialog, DialogContent, DialogDescription, DialogTitle} from '@/components/ui/dialog';
import {api, apiError} from './api';
import CategoryPicker from './category-picker';
import {downloadTemplate, readImport} from './files';
import {applyCategoryMappings, reviewImportRows} from './product-import';
import type {Product} from './data';

type Category = {id?: number; ar: string; en: string; parentId?: number | null; level?: number};
type EmbeddedImage = {row: number; status: string; count?: number; preview?: string};
type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lang: 'ar' | 'en';
  products: Product[];
  categories: Category[];
  onImported: () => void;
};

export default function ProductImportDialog({open, onOpenChange, lang, products, categories, onImported}: Props) {
  const en = lang === 'en';
  const t = (ar: string, english: string) => en ? english : ar;
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [excelRows, setExcelRows] = useState<number[]>([]);
  const [mappings, setMappings] = useState<Record<string, number>>({});
  const [embedded, setEmbedded] = useState<EmbeddedImage[]>([]);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const ids = useMemo(() => categories.flatMap(category => category.id ? [category.id] : []), [categories]);
  const pickerCategories = useMemo(() => categories.flatMap(category => category.id ? [{id: category.id, ar: category.ar, en: category.en, parentId: category.parentId, level: category.level}] : []), [categories]);
  const codes = useMemo(() => products.map(product => product.code), [products]);
  const mapped = useMemo(() => applyCategoryMappings(rows, mappings, ids), [rows, mappings, ids]);
  const sourceReview = useMemo(() => reviewImportRows(rows, excelRows, codes, ids, lang), [rows, excelRows, codes, ids, lang]);
  const review = useMemo(() => reviewImportRows(mapped, excelRows, codes, ids, lang), [mapped, excelRows, codes, ids, lang]);
  const pictureErrors = useMemo(() => embeddedPictureErrors(mapped, excelRows, embedded, en), [mapped, excelRows, embedded, en]);
  const errors = [...review.errors, ...pictureErrors];
  const sampleCategoryId = ids[0];

  const choose = async (next: File) => {
    setBusy(true);
    setNotice('');
    setName(next.name);
    setFile(next);
    setMappings({});
    setEmbedded([]);
    try {
      const result = await readImport(next, products, ids, lang);
      setRows(result.rows);
      setExcelRows(result.excelRows);
      if (next.name.toLowerCase().endsWith('.xlsx')) {
        const body = new FormData();
        body.set('file', next);
        const preview = await api<{images: EmbeddedImage[]}>('/api/admin/products/import-preview/', {method: 'POST', body});
        if (preview.ok) setEmbedded(preview.data.images || []);
        else setNotice(apiError(preview.data, t('تعذرت قراءة الصور المدمجة', 'Could not read embedded images')));
      } else {
        setNotice(t('ملفات xls لا تتضمن الصور المدمجة. استخدم xlsx أو ضع رابط الصورة في العمود.', 'xls files do not include embedded pictures. Use xlsx or put an image URL in the column.'));
      }
    } catch {
      setRows([]);
      setExcelRows([]);
      setNotice(t('تعذرت قراءة الملف', 'Could not read the file'));
    }
    setBusy(false);
  };

  const confirm = async () => {
    if (!file || errors.length || !mapped.length) return;
    setBusy(true);
    setNotice('');
    const xlsx = file.name.toLowerCase().endsWith('.xlsx');
    const body = new FormData();
    let result;
    if (xlsx) {
      body.set('file', file);
      body.set('lang', lang);
      body.set('category_map', JSON.stringify(mappings));
      result = await api<{created: number}>('/api/admin/products/bulk-import/', {method: 'POST', body});
    } else {
      result = await api<{created: number}>('/api/admin/products/bulk-import/', {method: 'POST', body: JSON.stringify({rows: mapped, lang, category_map: mappings})});
    }
    setBusy(false);
    if (!result.ok) {
      setNotice(apiError(result.data, t('تعذر الاستيراد', 'Could not import')));
      return;
    }
    toast.success(t('تم استيراد المنتجات', 'Products imported'));
    onImported();
    onOpenChange(false);
    setFile(null);
    setRows([]);
    setExcelRows([]);
    setMappings({});
    setEmbedded([]);
    setName('');
  };

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="import-dialog" dir={en ? 'ltr' : 'rtl'}>
      <DialogTitle>{t('استيراد المنتجات من Excel', 'Import products from Excel')}</DialogTitle>
      <DialogDescription>{t('استخدم قالب الغرابلي جلوبال الحالي، وأضف صورة عبر الرابط أو داخل عمود صورة المنتج.', 'Use the current Algharabli Global template and add a picture by URL or inside the product image column.')}</DialogDescription>
      <Button className="btn light" onClick={() => void downloadTemplate(lang, sampleCategoryId)}><Download size={17}/>{t('تنزيل القالب', 'Download template')}</Button>
      <label className="upload-zone"><Upload size={30}/><strong>{t('اختر ملف Excel', 'Choose an Excel file')}</strong><small><bdi>.xlsx · .xls</bdi>{name ? ` · ${name}` : ''}</small><input type="file" accept=".xlsx,.xls" onChange={event => {const next = event.target.files?.[0]; if (next) void choose(next);}}/></label>
      {notice && <p className="error-box" role="alert">{notice}</p>}
      {!!sourceReview.categoryProblems.length && <div className="import-map">
        <h3>{t('تصحيح التصنيفات', 'Correct categories')}</h3>
        <p>{t('معرّفات التصنيف غير الموجودة تبقى مرفوضة حتى تختار تصنيفًا موجودًا.', 'Unknown category ids stay blocked until you choose an existing category.')}</p>
        {sourceReview.categoryProblems.map(problem => <div key={problem.value || 'empty'} className="import-map-row">
          <div><strong><bdi>{problem.value || t('(فارغ)', '(empty)')}</bdi></strong><small>{t('الصفوف', 'Rows')} <bdi>{problem.rows.join(', ')}</bdi></small></div>
          <CategoryPicker categories={pickerCategories} value={mappings[problem.value] || null} onChange={id => setMappings(current => {
            const next = {...current};
            if (id) next[problem.value] = id;
            else delete next[problem.value];
            return next;
          })} en={en} label={t('التصنيف الصحيح', 'Correct category')} allowEmpty emptyLabel={t('اختر تصنيفًا', 'Choose a category')}/>
        </div>)}
      </div>}
      {!!errors.length && <ul className="import-errors">{errors.map(error => <li key={error}>{error}</li>)}</ul>}
      {!!mapped.length && <div className="table-box import-preview"><table><thead><tr><th>{t('الكود', 'Code')}</th><th>{t('كود المصنع', 'Factory Code')}</th><th>{t('الاسم', 'Name')}</th><th>{t('التصنيف', 'Category')}</th><th>{t('الصورة', 'Image')}</th><th>{t('السعر', 'Price')}</th></tr></thead><tbody>{mapped.slice(0, 20).map((row, index) => {
        const excelRow = excelRows[index];
        const picture = embedded.find(item => item.row === excelRow && item.preview);
        const url = String(row.Product_Image || '').trim();
        return <tr key={`${excelRow}-${String(row.Code)}`}><td><bdi>{String(row.Code || '')}</bdi></td><td><bdi>{String(row.Factory_Code || '—')}</bdi></td><td>{en ? String(row.Name_EN || '') : String(row.Name_AR || '')}</td><td><bdi>{String(row.Category_ID ?? '')}</bdi></td><td>{picture?.preview ? <img className="import-thumb" src={picture.preview} alt=""/> : url ? <span className="import-url"><bdi>{url}</bdi></span> : t('بدون صورة', 'No image')}</td><td><bdi>{String(row.Original_Price ?? row.Base_Price_ILS ?? '')} {String(row.Original_Currency || '')}</bdi></td></tr>;
      })}</tbody></table></div>}
      <div className="store-actions"><Button className="btn primary" disabled={busy || !mapped.length || !!errors.length} onClick={() => void confirm()}>{busy ? t('جارٍ الاستيراد…', 'Importing…') : t('اعتماد الاستيراد', 'Confirm import')}</Button></div>
    </DialogContent>
  </Dialog>;
}

function embeddedPictureErrors(rows: Record<string, unknown>[], excelRows: number[], images: EmbeddedImage[], en: boolean) {
  const errors: string[] = [];
  for (const image of images) {
    const label = en ? `Row ${image.row}` : `صف ${image.row}`;
    if (image.status === 'multiple') errors.push(en ? `${label}: multiple images are anchored to this row` : `${label}: أكثر من صورة مرتبطة بهذا الصف`);
    if (image.status === 'unsupported') errors.push(en ? `${label}: unsupported or corrupted image` : `${label}: صورة غير مدعومة أو تالفة`);
  }
  rows.forEach((row, index) => {
    const excelRow = excelRows[index];
    const embeddedOk = images.some(image => image.row === excelRow && image.status === 'ok');
    if (embeddedOk && String(row.Product_Image || '').trim()) {
      errors.push(en ? `Row ${excelRow}: row has both an image URL and an embedded image` : `صف ${excelRow}: الصف يحتوي على رابط صورة وصورة مدمجة معًا`);
    }
  });
  return errors;
}
