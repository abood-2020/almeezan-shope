export type GoogleAuthLang = 'ar' | 'en';

export function googleButtonLabel(lang: GoogleAuthLang) {
  return lang === 'en' ? 'Continue with Google' : 'المتابعة باستخدام Google';
}

export function googleAuthMessage(code: string, lang: GoogleAuthLang) {
  const english = lang === 'en';
  if (code === 'email_exists') {
    return english
      ? 'An account with this email already exists. Sign in with your username and password.'
      : 'يوجد حساب بهذا البريد. ادخل باسم المستخدم وكلمة المرور.';
  }
  if (code === 'unverified_email') {
    return english ? 'Google has not verified this email address.' : 'لم يتحقق Google من هذا البريد.';
  }
  if (code === 'inactive') {
    return english ? 'This trader account is inactive.' : 'حساب التاجر غير نشط.';
  }
  if (code === 'not_configured' || code === 'no_default_price_list') {
    return english ? 'Google sign-in is not available right now.' : 'تسجيل Google غير متاح الآن.';
  }
  if (code === 'expired') {
    return english ? 'The Google sign-in expired. Try again.' : 'انتهت صلاحية تسجيل Google. حاول مرة أخرى.';
  }
  return english ? 'Google sign-in could not be completed.' : 'تعذر إكمال تسجيل Google.';
}
