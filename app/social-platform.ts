export type SocialIconName = 'facebook' | 'instagram' | 'tiktok' | 'whatsapp' | 'wechat' | 'telegram' | 'youtube' | 'linkedin' | 'x' | 'link';

export type SocialLinkRecord = {
  id: number;
  name: string;
  url: string;
  sort_order?: number;
  is_active?: boolean;
};

const BY_NAME: Record<string, SocialIconName> = {
  facebook: 'facebook',
  فيسبوك: 'facebook',
  instagram: 'instagram',
  انستغرام: 'instagram',
  إنستغرام: 'instagram',
  انستقرام: 'instagram',
  tiktok: 'tiktok',
  'تيك توك': 'tiktok',
  whatsapp: 'whatsapp',
  واتساب: 'whatsapp',
  'واتس اب': 'whatsapp',
  wechat: 'wechat',
  'وي شات': 'wechat',
  ويتشات: 'wechat',
  telegram: 'telegram',
  تيليجرام: 'telegram',
  تلغرام: 'telegram',
  youtube: 'youtube',
  يوتيوب: 'youtube',
  linkedin: 'linkedin',
  لينكدإن: 'linkedin',
  'لينكد ان': 'linkedin',
  twitter: 'x',
  تويتر: 'x',
  x: 'x',
};

function compactName(value: string) {
  return value.trim().replace(/[._-]+/g, ' ').replace(/\s+/g, ' ');
}

function hostOf(value: string) {
  try {
    return new URL(value).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return '';
  }
}

function hostIcon(host: string): SocialIconName {
  if (host === 'facebook.com' || host.endsWith('.facebook.com') || host === 'fb.com' || host.endsWith('.fb.com') || host === 'fb.me') return 'facebook';
  if (host === 'instagram.com' || host.endsWith('.instagram.com')) return 'instagram';
  if (host === 'tiktok.com' || host.endsWith('.tiktok.com')) return 'tiktok';
  if (host === 'wa.me' || host === 'whatsapp.com' || host.endsWith('.whatsapp.com')) return 'whatsapp';
  if (host === 'wechat.com' || host.endsWith('.wechat.com') || host === 'weixin.qq.com' || host.endsWith('.weixin.qq.com')) return 'wechat';
  if (host === 't.me' || host === 'telegram.me' || host === 'telegram.org' || host.endsWith('.telegram.org')) return 'telegram';
  if (host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtu.be') return 'youtube';
  if (host === 'linkedin.com' || host.endsWith('.linkedin.com')) return 'linkedin';
  if (host === 'x.com' || host.endsWith('.x.com') || host === 'twitter.com' || host.endsWith('.twitter.com')) return 'x';
  return 'link';
}

export function socialPlatform(name: string, url = ''): SocialIconName {
  const spaced = compactName(name);
  const folded = spaced.toLowerCase();
  const named = BY_NAME[spaced] || BY_NAME[folded] || BY_NAME[folded.replace(/\s+/g, '')] || BY_NAME[name.trim()];
  if (named) return named;
  return hostIcon(hostOf(url));
}

export function safeHttpUrl(value: string) {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    if (!url.hostname) return '';
    return url.href;
  } catch {
    return '';
  }
}

export function visibleSocialLinks(source?: {social_links?: SocialLinkRecord[] | null; contact?: {facebook_url?: string; instagram_url?: string}} | null) {
  if (!source) return [];
  if (Array.isArray(source.social_links)) {
    return source.social_links.filter(link => link.is_active !== false && safeHttpUrl(link.url));
  }
  const legacy: SocialLinkRecord[] = [];
  const facebook = safeHttpUrl(source.contact?.facebook_url || '');
  const instagram = safeHttpUrl(source.contact?.instagram_url || '');
  if (facebook) legacy.push({id: -1, name: 'Facebook', url: facebook, sort_order: 0, is_active: true});
  if (instagram) legacy.push({id: -2, name: 'Instagram', url: instagram, sort_order: 1, is_active: true});
  return legacy;
}
