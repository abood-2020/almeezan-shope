export type ImportLang = 'ar' | 'en';

export const PRODUCT_TEMPLATE_FIELDS = [
  {key: 'Code', ar: 'كود المنتج', sample: 'RW-NEW-001'},
  {key: 'Name_AR', ar: 'اسم المنتج (عربي)', sample: 'منتج جديد'},
  {key: 'Name_EN', ar: 'اسم المنتج (إنجليزي)', sample: 'New product'},
  {key: 'Category_ID', ar: 'معرّف التصنيف', sample: ''},
  {key: 'Unit_AR', ar: 'وحدة البيع (عربي)', sample: 'قطعة'},
  {key: 'Unit_EN', ar: 'وحدة البيع (إنجليزي)', sample: 'piece'},
  {key: 'Min_Qty', ar: 'الحد الأدنى للكمية', sample: 6},
  {key: 'Original_Currency', ar: 'العملة الأصلية', sample: 'CNY'},
  {key: 'Original_Price', ar: 'السعر الأصلي', sample: 100},
  {key: 'Available', ar: 'متاح', sample: 1},
  {key: 'Description_AR', ar: 'الوصف (عربي)', sample: 'وصف المنتج'},
  {key: 'Description_EN', ar: 'الوصف (إنجليزي)', sample: 'Product description'},
  {key: 'Product_Image', ar: 'صورة المنتج', sample: ''},
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
  'السعر الأساسي (ils)': 'Base_Price_ILS',
  original_currency: 'Original_Currency',
  'العملة الأصلية': 'Original_Currency',
  original_price: 'Original_Price',
  'السعر الأصلي': 'Original_Price',
  available: 'Available',
  description_ar: 'Description_AR',
  description_en: 'Description_EN',
  product_image: 'Product_Image',
  'صورة المنتج': 'Product_Image',
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

export function fillProductTemplate(XLSX: {utils: {json_to_sheet: Function; book_new: Function; book_append_sheet: Function}}, lang: ImportLang, sampleCategoryId?: number) {
  const headers = templateHeaders(lang);
  const categorySample = Number.isInteger(sampleCategoryId) && Number(sampleCategoryId) > 0 ? Number(sampleCategoryId) : '';
  const sample = Object.fromEntries(PRODUCT_TEMPLATE_FIELDS.map((field, index) => [headers[index], field.key === 'Category_ID' ? categorySample : field.sample]));
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

export type CategoryProblem = {value: string; rows: number[]};
export type ImportInspection = {rows: Record<string, unknown>[]; errors: string[]; categoryProblems: CategoryProblem[]; excelRows: number[]};

function imageUrlProblem(value: unknown, lang: ImportLang) {
  const text = String(value ?? '').trim();
  if (!text) return '';
  try {
    const url = new URL(text);
    if (url.protocol === 'http:' || url.protocol === 'https:') return '';
  } catch {
    /* rejected below */
  }
  return phrase(lang, 'رابط الصورة غير صالح', 'invalid image URL');
}

export function applyCategoryMappings(rows: Record<string, unknown>[], mappings: Record<string, number>, categoryIds: number[]) {
  return rows.map(row => {
    const current = Number(row.Category_ID);
    if (Number.isInteger(current) && categoryIds.includes(current)) return row;
    const key = String(row.Category_ID ?? '').trim();
    const mapped = mappings[key];
    if (!Number.isInteger(mapped) || mapped < 1 || !categoryIds.includes(mapped)) return row;
    return {...row, Category_ID: mapped};
  });
}

export function inspectProductImport(matrix: unknown[][], existingCodes: Iterable<string>, categoryIds: number[], lang: ImportLang = 'ar'): ImportInspection {
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
  const optional = new Set(['Original_Currency', 'Original_Price', 'Base_Price_ILS', 'Product_Image']);
  for (const field of PRODUCT_TEMPLATE_FIELDS) {
    if (optional.has(field.key)) continue;
    if (!indexByField.has(field.key)) {
      errors.push(phrase(lang, `عمود مفقود: ${field.ar}`, `Missing column: ${field.key}`));
    }
  }
  if (!indexByField.has('Base_Price_ILS') && !(indexByField.has('Original_Currency') && indexByField.has('Original_Price'))) {
    errors.push(phrase(lang, 'أضف السعر الأصلي أو السعر الأساسي بالشيكل', 'Add Original_Price or Base_Price_ILS'));
  }
  const indexed = matrix.slice(1).map((row, offset) => ({cells: (row || []) as unknown[], excelRow: offset + 2}));
  const body = indexed.filter(item => item.cells.some(cell => String(cell ?? '').trim() !== ''));
  if (!body.length) errors.push(phrase(lang, 'الملف فارغ', 'The file is empty'));
  if (body.length > 1000) errors.push(phrase(lang, 'الحد الأقصى 1000 صف', 'Maximum 1000 rows'));
  const rows = body.map(item => {
    const record: Record<string, unknown> = {};
    for (const [field, index] of indexByField) record[field] = item.cells[index];
    return record;
  });
  const excelRows = body.map(item => item.excelRow);
  const reviewed = reviewImportRows(rows, excelRows, existingCodes, categoryIds, lang);
  return {rows, errors: [...errors, ...reviewed.errors], categoryProblems: reviewed.categoryProblems, excelRows};
}

export function reviewImportRows(rows: Record<string, unknown>[], excelRows: number[], existingCodes: Iterable<string>, categoryIds: number[], lang: ImportLang = 'ar') {
  const errors: string[] = [];
  const codes = new Set(existingCodes);
  const categoryGroups = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const problems: string[] = [];
    if (!row.Code || !row.Name_AR || !row.Name_EN || !row.Unit_AR || !row.Unit_EN) problems.push(phrase(lang, 'حقول مطلوبة', 'required fields'));
    if (codes.has(String(row.Code))) problems.push(phrase(lang, 'كود مكرر', 'duplicate code'));
    codes.add(String(row.Code));
    const categoryId = Number(row.Category_ID);
    if (!Number.isInteger(categoryId) || !categoryIds.includes(categoryId)) {
      const shown = String(row.Category_ID ?? '').trim();
      problems.push(phrase(lang, `معرّف التصنيف غير موجود: ${shown || '—'}`, `Category_ID ${shown || '(empty)'} does not exist`));
      const key = shown;
      categoryGroups.set(key, [...(categoryGroups.get(key) || []), excelRows[index]]);
    }
    const imageProblem = imageUrlProblem(row.Product_Image, lang);
    if (imageProblem) problems.push(imageProblem);
    if (!Number.isInteger(Number(row.Min_Qty)) || Number(row.Min_Qty) < 1) problems.push(phrase(lang, 'الحد الأدنى غير صالح', 'invalid minimum'));
    const legacy = row.Base_Price_ILS;
    const originalCurrency = String(row.Original_Currency ?? '').trim().toUpperCase();
    const originalPrice = row.Original_Price;
    const hasLegacy = legacy !== undefined && legacy !== '';
    const hasOriginal = originalCurrency !== '' || (originalPrice !== undefined && originalPrice !== '');
    if (!hasLegacy && !hasOriginal) problems.push(phrase(lang, 'سعر غير صالح', 'invalid price'));
    if (hasLegacy && (!Number.isFinite(Number(legacy)) || Number(legacy) < 0)) problems.push(phrase(lang, 'سعر غير صالح', 'invalid price'));
    if (hasOriginal) {
      const amount = Number(originalPrice);
      if (!['CNY', 'USD', 'ILS'].includes(originalCurrency) || !Number.isFinite(amount) || amount < 0) problems.push(phrase(lang, 'السعر الأصلي أو عملته غير صالحة', 'invalid original price'));
      else if (hasLegacy && originalCurrency !== 'ILS') problems.push(phrase(lang, 'لا تجمع السعر الأصلي بعملة غير الشيكل مع السعر الأساسي بالشيكل', 'ambiguous price columns'));
      else if (hasLegacy && originalCurrency === 'ILS' && Number(legacy) !== amount) problems.push(phrase(lang, 'السعر الأصلي لا يطابق السعر الأساسي بالشيكل', 'ambiguous price columns'));
    }
    if (!['0', '1'].includes(String(row.Available))) problems.push(phrase(lang, 'متاح يجب أن يكون 0 أو 1', 'Available must be 0 or 1'));
    if (problems.length) errors.push(`${phrase(lang, `صف ${excelRows[index]}`, `Row ${excelRows[index]}`)}: ${problems.join(' · ')}`);
  });
  const categoryProblems = [...categoryGroups].map(([value, problemRows]) => ({value, rows: problemRows}));
  return {errors, categoryProblems};
}
