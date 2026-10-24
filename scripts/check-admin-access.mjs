import {readFileSync} from 'node:fs';

const form = readFileSync(new URL('../app/trader-form.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const adapt = readFileSync(new URL('../app/adapt.ts', import.meta.url), 'utf8');
const required = [
  'تعيين كمدير',
  'Make Admin',
  'إلغاء صلاحيات المدير',
  'Revoke Admin Access',
  'تأكيد تعيين مدير',
  'Confirm Administrator Assignment',
  'هل أنت متأكد من تعيين هذا المستخدم كمدير للنظام؟',
  'Are you sure you want to make this user a system administrator?',
  'تأكيد التعيين',
  'Confirm Assignment',
  'تأكيد إلغاء صلاحيات المدير',
  'Confirm Administrator Access Removal',
  'هل أنت متأكد من إلغاء صلاحيات الإدارة لهذا المستخدم؟',
  'Are you sure you want to revoke this user\'s administrator access?',
  'تأكيد إلغاء الصلاحيات',
  'Revoke Access',
  'لا يمكن إلغاء صلاحيات آخر مدير نشط في النظام. يجب وجود مدير واحد على الأقل.',
  'Cannot revoke the last active administrator. At least one active administrator must remain.',
  'صلاحيات الحساب',
  'Account Access',
  'مدير النظام',
  'Administrator',
  'إدارة كاملة',
  'Full Administration',
];
const missing = required.filter(text => !form.includes(text));
if (missing.length) {
  console.error(missing.join('\n'));
  process.exit(1);
}
if (!page.includes("status-pill account-type") || !page.includes("مدير النظام")) {
  console.error('trader list is missing the administrator badge');
  process.exit(1);
}
if (!adapt.includes('admin: trader.is_staff === true')) {
  console.error('trader adapter does not read is_staff');
  process.exit(1);
}
const body = form.slice(form.indexOf('const body = {'), form.indexOf('setBusy(true)'));
if (body.includes('is_staff') || body.includes('is_superuser')) {
  console.error('save payload must not send privileged fields');
  process.exit(1);
}
console.log('admin access copy ok');
