import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const XLSX = require('xlsx');
const mod = await import(new URL('../app/product-import.ts', import.meta.url).href);

const {
  PRODUCT_TEMPLATE_FIELDS,
  canonicalHeader,
  fillProductTemplate,
  inspectProductImport,
  templateHeaders,
} = mod;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function matrixOf(book) {
  return XLSX.utils.sheet_to_json(book.Sheets[book.SheetNames[0]], {header: 1, raw: true});
}

const arabicBook = fillProductTemplate(XLSX, 'ar', 1);
const englishBook = fillProductTemplate(XLSX, 'en', 1);
const arabicMatrix = matrixOf(arabicBook);
const englishMatrix = matrixOf(englishBook);
const arabicHeaders = templateHeaders('ar');
const englishHeaders = templateHeaders('en');

assert(arabicBook.SheetNames[0] === 'Data', 'Arabic sheet name');
assert(englishBook.SheetNames[0] === 'Data', 'English sheet name');
assert(arabicBook.Workbook?.Views?.[0]?.RTL === true, 'Arabic workbook is RTL');
assert(!englishBook.Workbook?.Views?.[0]?.RTL, 'English workbook stays left to right');
assert(JSON.stringify(arabicMatrix[0]) === JSON.stringify(arabicHeaders), 'Arabic headers');
assert(JSON.stringify(englishMatrix[0]) === JSON.stringify(englishHeaders), 'English headers');
assert(englishHeaders.join('|') === PRODUCT_TEMPLATE_FIELDS.map(field => field.key).join('|'), 'English column order');
assert(arabicMatrix[1].join('|') === englishMatrix[1].join('|'), 'Sample values are not translated');
assert(arabicMatrix[1][0] === 'RW-NEW-001' && arabicMatrix[1][3] === 1 && arabicMatrix[1][7] === 'CNY' && arabicMatrix[1][8] === 100 && arabicMatrix[1][9] === 1, 'Sample contract');
assert(!englishHeaders.includes('Base_Price_ILS') && !arabicHeaders.includes('السعر الأساسي (ILS)'), 'Legacy ILS column was removed from the template');
assert(!englishHeaders.includes('Base_Price_USD') && !arabicHeaders.includes('السعر الأساسي (USD)'), 'USD column was not added');
assert(englishHeaders.at(-1) === 'Product_Image' && arabicHeaders.at(-1) === 'صورة المنتج', 'Image column is last');
assert(englishHeaders.slice(0, -1).join('|') === 'Code|Name_AR|Name_EN|Category_ID|Unit_AR|Unit_EN|Min_Qty|Original_Currency|Original_Price|Available|Description_AR|Description_EN', 'Existing columns stay in order');
const blankCategory = matrixOf(fillProductTemplate(XLSX, 'en'));
assert(blankCategory[1][3] !== 1, 'Sample category is not a hardcoded id');

for (const field of PRODUCT_TEMPLATE_FIELDS) {
  assert(canonicalHeader(`  ${field.ar}  `) === field.key, `Arabic alias ${field.key}`);
  assert(canonicalHeader(field.key) === field.key, `English alias ${field.key}`);
}
assert(canonicalHeader('Price_ILS') === 'Base_Price_ILS', 'Legacy price alias');
assert(canonicalHeader('price_ils') === 'Base_Price_ILS', 'Lowercase legacy price alias');

const categoryIds = [1];
const arabicImport = inspectProductImport(arabicMatrix, [], categoryIds, 'ar');
assert(arabicImport.errors.length === 0, `Arabic template rows: ${arabicImport.errors.join(' | ')}`);
assert(arabicImport.rows[0].Code === 'RW-NEW-001' && arabicImport.rows[0].Name_AR === 'منتج جديد' && arabicImport.rows[0].Original_Currency === 'CNY' && arabicImport.rows[0].Original_Price === 100, 'Arabic row mapping');

const englishImport = inspectProductImport(englishMatrix, [], categoryIds, 'en');
assert(englishImport.errors.length === 0, `English template rows: ${englishImport.errors.join(' | ')}`);
assert(englishImport.rows[0].Name_EN === 'New product' && englishImport.rows[0].Category_ID === 1, 'English row mapping');

const priceColumns = new Set(['Original_Currency', 'Original_Price']);
const withoutOriginal = englishHeaders.filter(header => !priceColumns.has(header));
const availableAt = withoutOriginal.indexOf('Available');
const legacyHeaders = [...withoutOriginal.slice(0, availableAt), 'Price_ILS', ...withoutOriginal.slice(availableAt)];
const sampleWithoutOriginal = englishMatrix[1].filter((_, index) => !priceColumns.has(englishHeaders[index]));
const legacyRow = [...sampleWithoutOriginal.slice(0, availableAt), 25, ...sampleWithoutOriginal.slice(availableAt)];
const legacy = [legacyHeaders, legacyRow];
const legacyImport = inspectProductImport(legacy, [], categoryIds, 'en');
assert(legacyImport.errors.length === 0, `Legacy import: ${legacyImport.errors.join(' | ')}`);
assert(legacyImport.rows[0].Base_Price_ILS === 25 && legacyImport.rows[0].Code === 'RW-NEW-001', 'Legacy price maps to ILS');

const conflictHeaders = [...englishHeaders, 'Base_Price_ILS'];
const conflictRow = [...englishMatrix[1], 25];
const conflictImport = inspectProductImport([conflictHeaders, conflictRow], [], categoryIds, 'en');
assert(conflictImport.errors.some(error => error.includes('ambiguous price columns')), 'Conflicting original and legacy prices are rejected');

const missing = [englishHeaders.filter(header => header !== 'Code'), englishMatrix[1].slice(1)];
const missingImport = inspectProductImport(missing, [], categoryIds, 'en');
assert(missingImport.errors.some(error => error.includes('Missing column: Code')), 'Missing column is reported');

const replaced = [['ProductCode', ...englishHeaders.slice(1)], ['RW-X', ...englishMatrix[1].slice(1)]];
const replacedImport = inspectProductImport(replaced, [], categoryIds, 'ar');
assert(replacedImport.errors.some(error => error.includes('عمود مفقود: كود المنتج')), 'Unknown replacement is a missing column');

const duplicate = [['Code', 'كود المنتج', ...englishHeaders.slice(1)], ['RW-1', 'RW-2', ...englishMatrix[1].slice(1)]];
const duplicateImport = inspectProductImport(duplicate, [], categoryIds, 'en');
assert(duplicateImport.errors.some(error => error.includes('Duplicate column: Code')), 'Duplicate aliases are rejected');

const badCategory = englishMatrix.map(row => row.slice());
badCategory[1][3] = 99;
const badCategoryImport = inspectProductImport(badCategory, ['RW-NEW-001'], categoryIds, 'en');
assert(badCategoryImport.errors.some(error => error.includes('Category_ID 99 does not exist')), 'Invalid category');
assert(badCategoryImport.categoryProblems[0].value === '99' && badCategoryImport.categoryProblems[0].rows.includes(2), 'Category problem identifies the value and row');
const mapped = mod.applyCategoryMappings(badCategoryImport.rows, {'99': 1}, categoryIds);
const mappedReview = mod.reviewImportRows(mapped, badCategoryImport.excelRows, ['RW-NEW-001'], categoryIds, 'en');
assert(mappedReview.categoryProblems.length === 0, 'Explicit category mapping clears the category error');
assert(mappedReview.errors.some(error => error.includes('duplicate code')), 'Mapping does not hide other errors');
const withoutImage = [englishHeaders.filter(header => header !== 'Product_Image'), englishMatrix[1].filter((_, index) => englishHeaders[index] !== 'Product_Image')];
const withoutImageImport = inspectProductImport(withoutImage, [], categoryIds, 'en');
assert(withoutImageImport.errors.length === 0, `Workbook without image column: ${withoutImageImport.errors.join(' | ')}`);
assert(badCategoryImport.errors.some(error => error.includes('duplicate code')), 'Existing code');

const badNumber = englishMatrix.map(row => row.slice());
badNumber[1][0] = 'RW-NUM';
badNumber[1][6] = 'abc';
const badNumberImport = inspectProductImport(badNumber, [], categoryIds, 'ar');
assert(badNumberImport.errors.some(error => error.includes('الحد الأدنى غير صالح')), 'Invalid minimum in Arabic');

console.log('product import template checks passed');
console.log(englishHeaders.join(', '));
