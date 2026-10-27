'use client';
import {useEffect, useState} from 'react';
import {ChevronDown, CircleHelp, Clapperboard, Phone, Plus, Store} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {api, apiError, resolveMedia} from './api';
import type {FaqItem, HomeSection, SocialLink, StoreContent} from './store-content';

type Props = {lang: 'ar' | 'en'; onSaved: (content: StoreContent) => void};
type SectionId = 'brand' | 'home' | 'faq' | 'contact';
type Translator = (ar: string, en: string) => string;

const SECTIONS: {id: SectionId; ar: string; en: string; descAr: string; descEn: string; icon: typeof Store}[] = [
  {id: 'brand', ar: 'الهوية', en: 'Brand Identity', descAr: 'اسم المتجر والشعار', descEn: 'Store name and logo', icon: Store},
  {id: 'home', ar: 'الصفحة الرئيسية', en: 'Homepage', descAr: 'فيديو الواجهة والعنوان', descEn: 'Hero video and heading', icon: Clapperboard},
  {id: 'faq', ar: 'الأسئلة الشائعة', en: 'Frequently Asked Questions', descAr: 'الأسئلة الظاهرة للتجار', descEn: 'Questions shown to traders', icon: CircleHelp},
  {id: 'contact', ar: 'التواصل', en: 'Contact', descAr: 'الهاتف وواتساب والعنوان', descEn: 'Phone, WhatsApp, and address', icon: Phone},
];

const emptyFaq = {question_ar: '', question_en: '', answer_ar: '', answer_en: ''};
let socialDraftId = -1;

export default function StoreSettings({lang, onSaved}: Props) {
  const en = lang === 'en';
  const t = (ar: string, eng: string) => en ? eng : ar;
  const [open, setOpen] = useState<SectionId | null>(null);
  const [form, setForm] = useState<StoreContent | null>(null);
  const [baseline, setBaseline] = useState<StoreContent | null>(null);
  const [files, setFiles] = useState<Record<string, File>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const [failed, setFailed] = useState(false);
  const [faqDraft, setFaqDraft] = useState(emptyFaq);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  useEffect(() => {
    let ignore = false;
    api<StoreContent>('/api/admin/settings/').then(result => {
      if (ignore) return;
      if (!result.ok) {setFailed(true); return;}
      setForm(result.data);
      setBaseline(result.data);
    });
    return () => {ignore = true;};
  }, []);

  if (failed) return <div className="panel store-settings"><p className="error-box" role="alert">{t('تعذر تحميل الإعدادات', 'Could not load settings')}</p></div>;
  if (!form || !baseline) return <div className="panel store-settings"><p>{t('جارٍ تحميل الإعدادات…', 'Loading settings…')}</p></div>;

  const hero = form.sections.find(section => section.key === 'hero');
  const savedHero = baseline.sections.find(section => section.key === 'hero');
  const patch = (recipe: (current: StoreContent) => StoreContent) => {setSaved(''); setForm(current => current ? recipe(current) : current);};
  const dirty = {
    brand: ['name_ar', 'name_en', 'logo_alt_ar', 'logo_alt_en'].some(key => form.brand[key as keyof typeof form.brand] !== baseline.brand[key as keyof typeof baseline.brand]) || !!files.logo,
    home: !!files.hero_video || !!files.hero_poster || form.hero.video_url !== baseline.hero.video_url || ['eyebrow_ar', 'eyebrow_en', 'title_ar', 'title_en', 'body_ar', 'body_en'].some(key => hero?.[key as keyof HomeSection] !== savedHero?.[key as keyof HomeSection]),
    faq: JSON.stringify(form.faqs) !== JSON.stringify(baseline.faqs) || Object.values(faqDraft).some(Boolean),
    contact: JSON.stringify(form.contact) !== JSON.stringify(baseline.contact) || JSON.stringify(form.social_links || []) !== JSON.stringify(baseline.social_links || []),
  };

  const remember = (next: StoreContent, part: SectionId) => {
    setBaseline(next);
    setForm(current => {
      if (!current) return next;
      if (part === 'brand') return {...current, brand: next.brand};
      if (part === 'home') {
        const savedSection = next.sections.find(section => section.key === 'hero');
        return {...current, hero: next.hero, sections: savedSection ? current.sections.map(section => section.key === 'hero' ? savedSection : section) : current.sections};
      }
      if (part === 'faq') return {...current, faqs: mergeFaqs(current.faqs, next.faqs)};
      return {...current, contact: next.contact, company_whatsapp_number: next.company_whatsapp_number, social_links: next.social_links || []};
    });
    onSaved(next);
    setSaved(t('تم الحفظ', 'Saved'));
    setError('');
  };

  const cancel = (part: SectionId) => {
    setError(''); setSaved('');
    setForm(current => {
      if (!current) return current;
      if (part === 'brand') return {...current, brand: baseline.brand};
      if (part === 'home') return {...current, hero: baseline.hero, sections: current.sections.map(section => section.key === 'hero' ? (savedHero || section) : section)};
      if (part === 'faq') return {...current, faqs: baseline.faqs};
      return {...current, contact: baseline.contact, company_whatsapp_number: baseline.company_whatsapp_number, social_links: baseline.social_links || []};
    });
    if (part === 'brand') setFiles(current => {const next = {...current}; delete next.logo; return next;});
    if (part === 'home') setFiles(current => {const next = {...current}; delete next.hero_video; delete next.hero_poster; return next;});
    if (part === 'faq') {setFaqDraft(emptyFaq); setAdding(false); setEditingId(null);}
  };

  const saveBrand = async () => {
    if (!form.brand.name_ar?.trim() || !form.brand.name_en?.trim()) {
      setError(t('اسم المتجر بالعربية والإنجليزية مطلوبان ولا يمكن تركهما فارغين', 'Arabic and English store names are required and cannot be blank'));
      return;
    }
    setBusy(true); setError(''); setSaved('');
    const body = new FormData();
    ['name_ar', 'name_en', 'logo_alt_ar', 'logo_alt_en'].forEach(key => body.set(key, String(form.brand[key as keyof typeof form.brand] || '')));
    if (files.logo) body.set('logo', files.logo);
    const result = await api<StoreContent>('/api/admin/settings/', {method: 'PATCH', body});
    setBusy(false);
    if (!result.ok) {setError(apiError(result.data, t('تعذر الحفظ', 'Could not save'))); return;}
    setFiles(current => {const next = {...current}; delete next.logo; return next;});
    remember(result.data, 'brand');
  };

  const saveHome = async () => {
    setBusy(true); setError(''); setSaved('');
    const media = new FormData();
    media.set('hero_video_url', form.hero.video_url || '');
    if (files.hero_video) media.set('hero_video', files.hero_video);
    if (files.hero_poster) media.set('hero_poster', files.hero_poster);
    const mediaResult = await api<StoreContent>('/api/admin/settings/', {method: 'PATCH', body: media});
    if (!mediaResult.ok) {setBusy(false); setError(apiError(mediaResult.data, t('تعذر حفظ الوسائط', 'Could not save media'))); return;}
    const sections = hero ? await api<StoreContent>('/api/admin/content/sections/', {method: 'PATCH', body: JSON.stringify({sections: [{key: 'hero', eyebrow_ar: hero.eyebrow_ar, eyebrow_en: hero.eyebrow_en, title_ar: hero.title_ar, title_en: hero.title_en, body_ar: hero.body_ar, body_en: hero.body_en}]})}) : {ok: true as const, data: mediaResult.data, status: 200};
    setBusy(false);
    if (!sections.ok) {setError(apiError(sections.data, t('تعذر حفظ الواجهة', 'Could not save the homepage'))); return;}
    setFiles(current => {const next = {...current}; delete next.hero_video; delete next.hero_poster; return next;});
    remember({...sections.data, hero: mediaResult.data.hero}, 'home');
  };

  const saveContact = async () => {
    setBusy(true); setError(''); setSaved('');
    const links = form.social_links || [];
    if (links.some(link => !link.name.trim() || !link.url.trim())) {setBusy(false); setError(t('أدخل اسم المعرّف والرابط لكل وسيلة', 'Enter a display name and URL for every link')); return;}
    const result = await api<StoreContent>('/api/admin/settings/', {method: 'PATCH', body: JSON.stringify({company_whatsapp_number: form.contact.whatsapp, phone: form.contact.phone, email: form.contact.email, address_ar: form.contact.address_ar, address_en: form.contact.address_en, social_links: links.map((link, index) => ({name: link.name.trim(), url: link.url.trim(), sort_order: index, is_active: link.is_active !== false}))})});
    setBusy(false);
    if (!result.ok) {setError(apiError(result.data, t('تعذر الحفظ', 'Could not save'))); return;}
    remember(result.data, 'contact');
  };

  const applyFaqs = (next: StoreContent, replacedId?: number) => {
    setBaseline(current => current ? {...current, faqs: next.faqs} : next);
    setForm(current => current ? {...current, faqs: mergeFaqs(current.faqs, next.faqs, replacedId)} : next);
    onSaved(next);
    setSaved(t('تم الحفظ', 'Saved'));
    setError('');
  };

  const moveFaq = (index: number, direction: number) => {
    const ids = form.faqs.map(item => item.id);
    const target = index + direction;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    setBusy(true);
    void api<StoreContent>('/api/admin/faqs/order/', {method: 'PUT', body: JSON.stringify({ids})}).then(result => {
      setBusy(false);
      if (!result.ok) {setError(apiError(result.data, t('تعذر إعادة الترتيب', 'Could not reorder'))); return;}
      applyFaqs(result.data);
    });
  };

  const setHeroCopy = (key: 'eyebrow_ar' | 'eyebrow_en' | 'title_ar' | 'title_en' | 'body_ar' | 'body_en', value: string) => patch(current => ({...current, sections: current.sections.map(section => section.key === 'hero' ? {...section, [key]: value} : section)}));

  return <div className="panel store-settings" dir={en ? 'ltr' : 'rtl'}>
    <p className="save-note" role="status">{saved}</p>
    {error && <p className="error-box" role="alert">{error}</p>}
    <div className="settings-accordion">
      {SECTIONS.map(section => {
        const expanded = open === section.id;
        const Icon = section.icon;
        return <section key={section.id} className={expanded ? 'accordion-item open' : 'accordion-item'}>
          <h2>
            <button type="button" className="accordion-trigger" aria-expanded={expanded} aria-controls={`settings-${section.id}`} id={`settings-trigger-${section.id}`} onClick={() => setOpen(expanded ? null : section.id)}>
              <span className="accordion-icon" aria-hidden="true"><Icon size={18}/></span>
              <span className="accordion-copy"><strong>{t(section.ar, section.en)}</strong><small>{t(section.descAr, section.descEn)}</small></span>
              {dirty[section.id] ? <span className="unsaved-pill">{t('غير محفوظ', 'Unsaved')}</span> : null}
              <ChevronDown className="accordion-chevron" aria-hidden="true" size={18}/>
            </button>
          </h2>
          <div className="accordion-panel" id={`settings-${section.id}`} role="region" aria-labelledby={`settings-trigger-${section.id}`} inert={expanded ? undefined : true}>
            <div className="accordion-panel-inner">
              {section.id === 'brand' && <div className="store-form">
                <div className="store-grid">
                  <label>{t('اسم المتجر بالعربية', 'Arabic store name')}<input value={form.brand.name_ar} onChange={e => patch(current => ({...current, brand: {...current.brand, name_ar: e.target.value}}))}/></label>
                  <label>{t('اسم المتجر بالإنجليزية', 'English store name')}<input value={form.brand.name_en} onChange={e => patch(current => ({...current, brand: {...current.brand, name_en: e.target.value}}))}/></label>
                  <label>{t('النص البديل للشعار بالعربية', 'Arabic logo alt text')}<input value={form.brand.logo_alt_ar} onChange={e => patch(current => ({...current, brand: {...current.brand, logo_alt_ar: e.target.value}}))}/></label>
                  <label>{t('النص البديل للشعار بالإنجليزية', 'English logo alt text')}<input value={form.brand.logo_alt_en} onChange={e => patch(current => ({...current, brand: {...current.brand, logo_alt_en: e.target.value}}))}/></label>
                </div>
                <label>{t('شعار المتجر', 'Store logo')}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={e => {const file = e.target.files?.[0]; if (file) setFiles(current => ({...current, logo: file}));}}/><Preview file={files.logo} saved={form.brand.logo} alt={en ? form.brand.logo_alt_en : form.brand.logo_alt_ar}/></label>
                <Actions t={t} busy={busy} onSave={() => void saveBrand()} onCancel={() => cancel('brand')}/>
              </div>}
              {section.id === 'home' && <div className="store-form">
                <label>{t('رابط فيديو مباشر', 'Direct video URL')}<input dir="ltr" value={form.hero.video_url} onChange={e => patch(current => ({...current, hero: {...current.hero, video_url: e.target.value}}))} placeholder="https://…/video.mp4"/></label>
                <div className="store-grid">
                  <label>{t('رفع فيديو', 'Upload video')}<input type="file" accept="video/mp4,video/webm" onChange={e => {const file = e.target.files?.[0]; if (file) setFiles(current => ({...current, hero_video: file}));}}/>{(files.hero_video || form.hero.video) ? <small>{files.hero_video?.name || t('فيديو محفوظ', 'Saved video')}</small> : null}</label>
                  <label>{t('صورة بديلة', 'Poster image')}<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => {const file = e.target.files?.[0]; if (file) setFiles(current => ({...current, hero_poster: file}));}}/><Preview file={files.hero_poster} saved={form.hero.poster} alt=""/></label>
                </div>
                {hero && <div className="store-grid">
                  <label>{t('وسم الواجهة بالعربية', 'Arabic hero tag')}<input value={hero.eyebrow_ar} onChange={e => setHeroCopy('eyebrow_ar', e.target.value)}/></label>
                  <label>{t('وسم الواجهة بالإنجليزية', 'English hero tag')}<input value={hero.eyebrow_en} onChange={e => setHeroCopy('eyebrow_en', e.target.value)}/></label>
                  <label>{t('العنوان الرئيسي بالعربية', 'Arabic main heading')}<input value={hero.title_ar} onChange={e => setHeroCopy('title_ar', e.target.value)}/></label>
                  <label>{t('العنوان الرئيسي بالإنجليزية', 'English main heading')}<input value={hero.title_en} onChange={e => setHeroCopy('title_en', e.target.value)}/></label>
                  <label>{t('الوصف بالعربية', 'Arabic subtitle')}<textarea value={hero.body_ar} onChange={e => setHeroCopy('body_ar', e.target.value)}/></label>
                  <label>{t('الوصف بالإنجليزية', 'English subtitle')}<textarea value={hero.body_en} onChange={e => setHeroCopy('body_en', e.target.value)}/></label>
                </div>}
                <Actions t={t} busy={busy} onSave={() => void saveHome()} onCancel={() => cancel('home')}/>
              </div>}
              {section.id === 'faq' && <div className="store-form">
                {adding ? <div className="faq-editor">
                  <FaqFields t={t} item={faqDraft} onChange={setFaqDraft}/>
                  <div className="store-actions">
                    <Button type="button" className="btn primary" disabled={busy} onClick={async () => {setBusy(true); setError(''); const result = await api<StoreContent>('/api/admin/faqs/', {method: 'POST', body: JSON.stringify(faqDraft)}); setBusy(false); if (!result.ok) {setError(apiError(result.data, t('أدخل السؤال والجواب باللغتين', 'Enter the question and answer in both languages'))); return;} setFaqDraft(emptyFaq); setAdding(false); applyFaqs(result.data);}}>{t('حفظ السؤال', 'Save question')}</Button>
                    <Button type="button" className="btn light" disabled={busy} onClick={() => {setFaqDraft(emptyFaq); setAdding(false);}}>{t('إلغاء', 'Cancel')}</Button>
                  </div>
                </div> : <Button type="button" className="btn light" onClick={() => {setAdding(true); setEditingId(null);}}><Plus size={16}/>{t('إضافة سؤال', 'Add FAQ')}</Button>}
                <div className="faq-list">
                  {form.faqs.map((item, index) => {
                    const expandedFaq = editingId === item.id;
                    return <article key={item.id} className={expandedFaq ? 'faq-row open' : 'faq-row'}>
                      <button type="button" className="faq-summary" aria-expanded={expandedFaq} onClick={() => {setEditingId(expandedFaq ? null : item.id); setAdding(false);}}>
                        <strong>{(en ? item.question_en : item.question_ar) || t('سؤال بدون عنوان', 'Untitled question')}</strong>
                        <span className={item.is_active ? 'status-pill on' : 'status-pill'}>{item.is_active ? t('منشور', 'Published') : t('مخفي', 'Hidden')}</span>
                        <span className="faq-order">{index + 1}</span>
                      </button>
                      {expandedFaq && <div className="faq-editor">
                        <FaqFields t={t} item={item} onChange={next => patch(current => ({...current, faqs: current.faqs.map(row => row.id === item.id ? {...row, ...next} : row)}))}/>
                        <label className="check-label"><input type="checkbox" checked={item.is_active} onChange={e => patch(current => ({...current, faqs: current.faqs.map(row => row.id === item.id ? {...row, is_active: e.target.checked} : row)}))}/>{t('منشور', 'Published')}</label>
                        <label>{t('ترتيب العرض', 'Display order')}<input inputMode="numeric" value={String(item.sort_order)} onChange={e => patch(current => ({...current, faqs: current.faqs.map(row => row.id === item.id ? {...row, sort_order: Number(e.target.value.replace(/\D/g, '')) || 0} : row)}))}/></label>
                        <div className="store-actions">
                          <Button type="button" className="btn light" disabled={index === 0 || busy} onClick={() => moveFaq(index, -1)}>{t('أعلى', 'Up')}</Button>
                          <Button type="button" className="btn light" disabled={index === form.faqs.length - 1 || busy} onClick={() => moveFaq(index, 1)}>{t('أسفل', 'Down')}</Button>
                          <Button type="button" className="btn primary" disabled={busy} onClick={async () => {setBusy(true); const result = await api<StoreContent>(`/api/admin/faqs/${item.id}/`, {method: 'PATCH', body: JSON.stringify(item)}); setBusy(false); if (!result.ok) {setError(apiError(result.data, t('تعذر حفظ السؤال', 'Could not save the question'))); return;} applyFaqs(result.data, item.id);}}>{t('حفظ', 'Save')}</Button>
                          <Button type="button" className="btn light" disabled={busy} onClick={async () => {if (!window.confirm(t('حذف هذا السؤال؟', 'Delete this question?'))) return; setBusy(true); const result = await api<StoreContent>(`/api/admin/faqs/${item.id}/`, {method: 'DELETE'}); setBusy(false); if (!result.ok) {setError(apiError(result.data, t('تعذر حذف السؤال', 'Could not delete the question'))); return;} setEditingId(null); applyFaqs(result.data);}}>{t('حذف', 'Delete')}</Button>
                        </div>
                      </div>}
                    </article>;
                  })}
                </div>
                <div className="store-actions"><Button type="button" className="btn light" disabled={busy} onClick={() => cancel('faq')}>{t('إلغاء', 'Cancel')}</Button></div>
              </div>}
              {section.id === 'contact' && <div className="store-form">
                <div className="store-grid">
                  <label>{t('هاتف الشركة', 'Company phone')}<input dir="ltr" value={form.contact.phone} onChange={e => patch(current => ({...current, contact: {...current.contact, phone: e.target.value}}))}/></label>
                  <label>{t('واتساب مع رمز الدولة', 'WhatsApp with country code')}<input dir="ltr" value={form.contact.whatsapp} onChange={e => patch(current => ({...current, company_whatsapp_number: e.target.value.replace(/\D/g, ''), contact: {...current.contact, whatsapp: e.target.value}}))}/></label>
                  <label>{t('البريد', 'Email')}<input dir="ltr" value={form.contact.email} onChange={e => patch(current => ({...current, contact: {...current.contact, email: e.target.value}}))}/></label>
                  <label>{t('العنوان بالعربية', 'Arabic address')}<input value={form.contact.address_ar} onChange={e => patch(current => ({...current, contact: {...current.contact, address_ar: e.target.value}}))}/></label>
                  <label>{t('العنوان بالإنجليزية', 'English address')}<input value={form.contact.address_en} onChange={e => patch(current => ({...current, contact: {...current.contact, address_en: e.target.value}}))}/></label>
                </div>
                <SocialLinks t={t} en={en} links={form.social_links || []} onChange={recipe => patch(current => ({...current, social_links: recipe(current.social_links || []).map((link, index) => ({...link, sort_order: index}))}))}/>
                <Actions t={t} busy={busy} onSave={() => void saveContact()} onCancel={() => cancel('contact')}/>
              </div>}
            </div>
          </div>
        </section>;
      })}
    </div>
  </div>;
}

function mergeFaqs(current: FaqItem[], saved: FaqItem[], replacedId?: number) {
  const savedById = new Map(saved.map(item => [item.id, item]));
  const kept = current.filter(item => savedById.has(item.id)).map(item => {
    const fresh = savedById.get(item.id)!;
    return replacedId === item.id ? fresh : {...item, sort_order: fresh.sort_order};
  });
  const known = new Set(kept.map(item => item.id));
  const order = saved.map(item => item.id);
  return [...kept, ...saved.filter(item => !known.has(item.id))].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
}

function Actions({t, busy, onSave, onCancel, saveLabel}: {t: Translator; busy: boolean; onSave: () => void; onCancel: () => void; saveLabel?: string}) {
  return <div className="store-actions"><Button type="button" className="btn primary" disabled={busy} onClick={onSave}>{busy ? t('جارٍ الحفظ…', 'Saving…') : (saveLabel || t('حفظ', 'Save'))}</Button><Button type="button" className="btn light" disabled={busy} onClick={onCancel}>{t('إلغاء', 'Cancel')}</Button></div>;
}

function FaqFields({t, item, onChange}: {t: Translator; item: {question_ar: string; question_en: string; answer_ar: string; answer_en: string}; onChange: (item: {question_ar: string; question_en: string; answer_ar: string; answer_en: string}) => void}) {
  return <div className="store-grid">
    <label>{t('السؤال بالعربية', 'Arabic question')}<input value={item.question_ar} onChange={e => onChange({...item, question_ar: e.target.value})}/></label>
    <label>{t('السؤال بالإنجليزية', 'English question')}<input value={item.question_en} onChange={e => onChange({...item, question_en: e.target.value})}/></label>
    <label>{t('الجواب بالعربية', 'Arabic answer')}<textarea value={item.answer_ar} onChange={e => onChange({...item, answer_ar: e.target.value})}/></label>
    <label>{t('الجواب بالإنجليزية', 'English answer')}<textarea value={item.answer_en} onChange={e => onChange({...item, answer_en: e.target.value})}/></label>
  </div>;
}

function SocialLinks({t, links, onChange}: {t: Translator; en: boolean; links: SocialLink[]; onChange: (recipe: (links: SocialLink[]) => SocialLink[]) => void}) {
  return <section className="social-editor">
    <div className="social-editor-head">
      <h3>{t('وسائل التواصل الاجتماعي', 'Social Media & Contact Links')}</h3>
      <Button type="button" className="btn light" onClick={() => onChange(current => [...current, {id: socialDraftId--, name: '', url: '', sort_order: current.length, is_active: true}])}><Plus size={16}/>{t('إضافة وسيلة تواصل', 'Add Social Link')}</Button>
    </div>
    {links.map((link, index) => <div key={link.id} className="social-editor-row">
      <label>{t('اسم المعرّف', 'Display Name')}<input value={link.name} onChange={event => onChange(current => current.map(item => item.id === link.id ? {...item, name: event.target.value} : item))}/></label>
      <label>{t('عنوان الرابط', 'URL')}<input dir="ltr" value={link.url} placeholder="https://" onChange={event => onChange(current => current.map(item => item.id === link.id ? {...item, url: event.target.value} : item))}/></label>
      <div className="social-editor-foot">
      <label className="check-label"><input type="checkbox" checked={link.is_active !== false} onChange={event => onChange(current => current.map(item => item.id === link.id ? {...item, is_active: event.target.checked} : item))}/>{t('ظاهر', 'Visible')}</label>
      <div className="store-actions">
        <Button type="button" className="btn light" disabled={index === 0} onClick={() => onChange(current => {const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next;})}>{t('أعلى', 'Up')}</Button>
        <Button type="button" className="btn light" disabled={index === links.length - 1} onClick={() => onChange(current => {const next = [...current]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; return next;})}>{t('أسفل', 'Down')}</Button>
        <Button type="button" className="btn light" onClick={() => {if (!window.confirm(t('حذف وسيلة التواصل هذه؟', 'Delete this social link?'))) return; onChange(current => current.filter(item => item.id !== link.id));}}>{t('حذف', 'Delete')}</Button>
      </div>
      </div>
    </div>)}
  </section>;
}

function Preview({file, saved, alt}: {file?: File; saved: string; alt: string}) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!file) {setUrl(resolveMedia(saved)); return;}
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file, saved]);
  return url ? <img className="media-preview" src={url} alt={alt}/> : null;
}
