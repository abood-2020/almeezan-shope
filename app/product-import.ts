export type ImportLang = 'ar' | 'en';

export const PRODUCT_TEMPLATE_FIELDS = [
  {key: 'Code', ar: 'كود المنتج', sample: 'RW-NEW-001'},
  {key: 'Name_AR', ar: 'اسم المنتج (عربي)', sample: 'منتج جديد'},
  {key: 'Name_EN', ar: 'اسم المنتج (إنجليزي)', sample: 'New product'},
  {key: 'Category_ID', ar: 'معرّف التصنيف', sample: 1},
  {key: 'Unit_AR', ar: 'وحدة البيع (عربي)', sample: 'قطعة'},
  {key: 'Unit_EN', ar: 'وحدة البيع (إنجليزي)', sample: 'piece'},
  {key: 'Min_Qty', ar: 'الحد الأدنى للكمية', sample: 6},
  {key: 'Base_Price_ILS', ar: 'السعر الأساسي (ILS)', sample: 25},
  {key: 'Available', ar: 'متاح', sample: 1},
  {key: 'Description_AR', ar: 'الوصف (عربي)', sample: 'وصف المنتج'},
  {key: 'Description_EN', ar: 'الوصف (إنجليزي)', sample: 'Product description'},
] as const;

const LEGACY_HEADERS: Record<string, string> = {
  code: 'Code',
  name_ar: 'Name_AR',
  name_en: 'Name_EN',
  category_id: 'Category_ID',
  unit_ar: 'Unit_AR',
  unit_en: 'Unit_EN',
  min_qty: 'Min_Qty',
  base_price_ils: 'Base_Price_ILS',
  price_ils: 'Base_Price_ILS',
  available: 'Available',
  description_ar: 'Description_AR',
  description_en: 'Description_EN',
};

export const productTemplateColumns = PRODUCT_TEMPLATE_FIELDS.map(field => field.key);

export function importLanguage(lang: string | null | undefined): ImportLang {
  return String(lang || '').toLowerCase().startsWith('en') ? 'en' : 'ar';
}

export function cleanHeader(value: unknown) {
  return String(value ?? '').trim().replace(/\s+/g, ' ');
}

export function canonicalHeader(label: unknown) {
  const text = cleanHeader(label);
  if (!text) return null;
  const field = PRODUCT_TEMPLATE_FIELDS.find(item => item.key === text || item.ar === text);
  if (field) return field.key;
  return LEGACY_HEADERS[text.toLowerCase()] || null;
}

export function templateHeaders(lang: ImportLang) {
  return PRODUCT_TEMPLATE_FIELDS.map(field => (lang === 'en' ? field.key : field.ar));
}

export function fillProductTemplate(XLSX: {utils: {json_to_sheet: Function; book_new: Function; book_append_sheet: Function}}, lang: ImportLang) {
  const headers = templateHeaders(lang);
  const sample = Object.fromEntries(PRODUCT_TEMPLATE_FIELDS.map((field, index) => [headers[index], field.sample]));
  const sheet = XLSX.utils.json_to_sheet([sample], {header: headers});
  sheet['!cols'] = headers.map(() => ({wch: 24}));
  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, sheet, 'Data');
  if (lang !== 'en') book.Workbook = {Views: [{RTL: true}]};
  return book;
}

function phrase(lang: ImportLang, ar: string, en: string) {
  return lang === 'en' ? en : ar;
}

function fieldLabel(lang: ImportLang, key: string) {
  const field = PRODUCT_TEMPLATE_FIELDS.find(item => item.key === key);
  if (!field) return key;
  return lang === 'en' ? field.key : field.ar;
}

export function inspectProductImport(matrix: unknown[][], existingCodes: Iterable<string>, categoryIds: number[], lang: ImportLang = 'ar') {
  const header = ((matrix[0] || []) as unknown[]);
  const errors: string[] = [];
  const indexByField = new Map<string, number>();
  header.forEach((cell, index) => {
    const field = canonicalHeader(cell);
    if (!field) return;
    if (indexByField.has(field)) {
      errors.push(phrase(lang, `عمود مكرر: ${fieldLabel(lang, field)}`, `Duplicate column: ${field}`));
      return;
    }
    indexByField.set(field, index);
  });
  for (const field of PRODUCT_TEMPLATE_FIELDS) {
    if (!indexByField.has(field.key)) {
      errors.push(phrase(lang, `عمود مفقود: ${field.ar}`, `Missing column: ${field.key}`));
    }
  }
  const body = matrix.slice(1).filter(row => (row || []).some(cell => String(cell ?? '').trim() !== ''));
  if (!body.length) errors.push(phrase(lang, 'الملف فارغ', 'The file is empty'));
  if (body.length > 1000) errors.push(phrase(lang, 'الحد الأقصى 1000 صف', 'Maximum 1000 rows'));
  const codes = new Set(existingCodes);
  const rows = body.map(row => {
    const record: Record<string, unknown> = {};
    for (const [field, index] of indexByField) record[field] = (row as unknown[])[index];
    return record;
  });
  rows.forEach((row, index) => {
    const problems: string[] = [];
    if (!row.Code || !row.Name_AR || !row.Name_EN || !row.Unit_AR || !row.Unit_EN) problems.push(phrase(lang, 'حقول مطلوبة', 'required fields'));
    if (codes.has(String(row.Code))) problems.push(phrase(lang, 'كود مكرر', 'duplicate code'));
    codes.add(String(row.Code));
    if (!Number.isInteger(Number(row.Category_ID)) || !categoryIds.includes(Number(row.Category_ID))) problems.push(phrase(lang, 'معرّف التصنيف غير موجود', 'Category_ID must match an existing category id'));
    if (!Number.isInteger(Number(row.Min_Qty)) || Number(row.Min_Qty) < 1) problems.push(phrase(lang, 'الحد الأدنى غير صالح', 'invalid minimum'));
    const price = row.Base_Price_ILS;
    if (price === undefined || price === '' || !Number.isFinite(Number(price)) || Number(price) < 0) problems.push(phrase(lang, 'سعر غير صالح', 'invalid price'));
    if (!['0', '1'].includes(String(row.Available))) problems.push(phrase(lang, 'متاح يجب أن يكون 0 أو 1', 'Available must be 0 or 1'));
    if (problems.length) errors.push(`${phrase(lang, `صف ${index + 2}`, `Row ${index + 2}`)}: ${problems.join(' · ')}`);
  });
  return {rows, errors};
}
