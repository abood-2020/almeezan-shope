import {googleAuthMessage, googleButtonLabel} from '../app/google-auth.ts';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(googleButtonLabel('ar') === 'المتابعة باستخدام Google', 'Arabic button label');
assert(googleButtonLabel('en') === 'Continue with Google', 'English button label');
assert(googleAuthMessage('email_exists', 'en').includes('username and password'), 'Email conflict stays on the existing login');
assert(googleAuthMessage('email_exists', 'ar').includes('اسم المستخدم'), 'Arabic email conflict');
assert(googleAuthMessage('unverified_email', 'en').includes('verified'), 'Unverified email');
assert(googleAuthMessage('expired', 'ar').includes('انتهت'), 'Expired token');
assert(!googleAuthMessage('invalid', 'en').includes('token'), 'Errors do not echo a token');

console.log('google auth message checks passed');
