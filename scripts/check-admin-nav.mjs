import fs from 'node:fs';

const source = fs.readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const start = source.indexOf("{id:'overview'");
if (start < 0) throw new Error('sidebar array was not found');
const ids = [...source.slice(start, start + 1400).matchAll(/id:'([^']+)'/g)].map(match => match[1]);
const expected = ['overview', 'categories', 'products', 'merchants', 'prices', 'currencies', 'orders', 'invoices', 'settings'];
if (ids.slice(0, expected.length).join(',') !== expected.join(',')) {
  throw new Error(`sidebar order is ${ids.slice(0, expected.length).join(',')}`);
}
const labels = [...source.slice(start, start + 1400).matchAll(/ar:'([^']+)',en:'([^']+)'/g)].map(match => `${match[1]}/${match[2]}`);
const expectedLabels = [
  'نظرة عامة/Overview',
  'التصنيفات/Categories',
  'المنتجات/Products',
  'التجار/Traders',
  'قوائم الأسعار/Price lists',
  'العملات/Currencies',
  'الطلبات/Orders',
  'الفواتير والملفات/Invoices & files',
  'إعدادات المتجر/Store settings',
];
if (labels.slice(0, expectedLabels.length).join('|') !== expectedLabels.join('|')) {
  throw new Error(`sidebar labels are ${labels.slice(0, expectedLabels.length).join('|')}`);
}
console.log('admin navigation order checks passed');
