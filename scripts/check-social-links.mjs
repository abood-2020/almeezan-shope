const mod = await import(new URL('../app/social-platform.ts', import.meta.url).href);
const {socialPlatform, visibleSocialLinks, safeHttpUrl} = mod;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(socialPlatform('Facebook', 'https://example.com') === 'facebook', 'name wins over an unrelated host');
assert(socialPlatform('Instagram') === 'instagram', 'instagram name');
assert(socialPlatform('تيك توك') === 'tiktok', 'tiktok name');
assert(socialPlatform('WhatsApp') === 'whatsapp', 'whatsapp name');
assert(socialPlatform('WeChat') === 'wechat', 'wechat name');
assert(socialPlatform('Telegram') === 'telegram', 'telegram name');
assert(socialPlatform('YouTube') === 'youtube', 'youtube name');
assert(socialPlatform('LinkedIn') === 'linkedin', 'linkedin name');
assert(socialPlatform('Twitter') === 'x' && socialPlatform('X') === 'x', 'x and twitter');
assert(socialPlatform('Future Platform', 'https://facebook.com/store') === 'facebook', 'unknown name uses a trusted host');
assert(socialPlatform('Future Platform', 'https://example.com/store') === 'link', 'unknown platform gets the generic icon');
assert(safeHttpUrl('javascript:alert(1)') === '', 'javascript urls are not rendered');
assert(safeHttpUrl('https://example.com/a') === 'https://example.com/a', 'https urls stay');

const migrated = visibleSocialLinks({
  social_links: [
    {id: 1, name: 'Facebook', url: 'https://facebook.com/one', is_active: true},
    {id: 2, name: 'Facebook', url: 'https://facebook.com/two', is_active: true},
    {id: 3, name: 'Hidden', url: 'https://example.com/hidden', is_active: false},
  ],
  contact: {facebook_url: 'https://facebook.com/legacy', instagram_url: 'https://instagram.com/legacy'},
});
assert(migrated.map(link => link.id).join(',') === '1,2', 'active links stay separate and legacy fields are not repeated');
const legacy = visibleSocialLinks({contact: {facebook_url: 'https://facebook.com/legacy', instagram_url: 'javascript:alert(1)'}});
assert(legacy.length === 1 && legacy[0].name === 'Facebook', 'legacy fallback keeps only a safe facebook url');
console.log('social link checks passed');
