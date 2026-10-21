export type CopyBlock = {key: string; sort_order: number; title_ar: string; title_en: string; body_ar: string; body_en: string};
export type HomeSection = {
  key: string; visible: boolean; sort_order: number;
  eyebrow_ar: string; eyebrow_en: string; title_ar: string; title_en: string; body_ar: string; body_en: string;
  cta_ar: string; cta_en: string; cta_target: string;
  secondary_cta_ar: string; secondary_cta_en: string; secondary_cta_target: string;
  aside_title_ar: string; aside_title_en: string; aside_body_ar: string; aside_body_en: string;
  blocks: CopyBlock[];
};
export type ContentPage = {
  key: string;
  eyebrow_ar: string; eyebrow_en: string; title_ar: string; title_en: string; body_ar: string; body_en: string;
  intro_title_ar: string; intro_title_en: string; intro_body_ar: string; intro_body_en: string;
  cta_ar: string; cta_en: string;
  faq_eyebrow_ar: string; faq_eyebrow_en: string; faq_title_ar: string; faq_title_en: string;
  faq_intro_ar: string; faq_intro_en: string;
  blocks: CopyBlock[];
};
export type FaqItem = {id: number; question_ar: string; question_en: string; answer_ar: string; answer_en: string; sort_order: number; is_active: boolean};
export type SocialLink = {id: number; name: string; url: string; sort_order: number; is_active: boolean};
export type StoreContent = {
  company_whatsapp_number: string;
  brand: {name_ar: string; name_en: string; tagline_ar: string; tagline_en: string; header_caption_ar: string; header_caption_en: string; logo: string; logo_alt_ar: string; logo_alt_en: string; favicon: string};
  contact: {phone: string; whatsapp: string; email: string; address_ar: string; address_en: string; instagram_url: string; facebook_url: string};
  social_links: SocialLink[];
  seo: {title_ar: string; title_en: string; description_ar: string; description_en: string; image: string};
  hero: {video: string; video_url: string; poster: string};
  footer: {explore_ar: string; explore_en: string; account_ar: string; account_en: string; copyright_ar: string; copyright_en: string; note_ar: string; note_en: string; place_ar: string; place_en: string};
  nav: Record<string, string>;
  sections: HomeSection[];
  pages: ContentPage[];
  faqs: FaqItem[];
};

export const CTA_TARGETS = ['', 'catalog', 'portal', 'whatsapp', 'products', 'contact', 'traders', 'export', 'info'] as const;

function visibleTitle(brand: string, seoTitle: string) {
  const name = brand.trim();
  const stored = seoTitle.trim();
  if (!name) return stored;
  const parts = stored.split('|').map(part => part.trim()).filter(Boolean);
  if (parts.length > 1) return [name, ...parts.slice(1)].join(' | ');
  if (!stored || stored === name) return name;
  return `${name} | ${stored}`;
}

export function applyDocumentMeta(content: StoreContent, english: boolean, media: (value: string) => string) {
  const title = visibleTitle(english ? content.brand.name_en : content.brand.name_ar, english ? content.seo.title_en : content.seo.title_ar);
  const description = english ? content.seo.description_en : content.seo.description_ar;
  if (title) document.title = title;
  const ensure = (selector: string, create: () => HTMLElement) => document.head.querySelector(selector) || document.head.appendChild(create());
  const descriptionTag = ensure('meta[name="description"]', () => {const tag = document.createElement('meta'); tag.setAttribute('name', 'description'); return tag;});
  descriptionTag.setAttribute('content', description || '');
  const icon = media(content.brand.favicon);
  if (icon) {
    const link = ensure('link[rel="icon"]', () => {const tag = document.createElement('link'); tag.setAttribute('rel', 'icon'); return tag;}) as HTMLLinkElement;
    link.href = icon;
  }
  const setProperty = (property: string, value: string) => {
    if (!value) return;
    const tag = ensure(`meta[property="${property}"]`, () => {const node = document.createElement('meta'); node.setAttribute('property', property); return node;});
    tag.setAttribute('content', value);
  };
  setProperty('og:title', title);
  setProperty('og:description', description);
  setProperty('og:image', media(content.seo.image));
}
