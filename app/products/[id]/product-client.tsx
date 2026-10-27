'use client';

import {useEffect, useMemo, useState} from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Copy,
  Globe2,
  Minus,
  Plus,
  Share2,
  ShoppingBag,
} from 'lucide-react';
import {toast} from 'sonner';
import {getApiBase} from '@/app/api';

type DisplayCurrency = 'USD' | 'ILS' | 'CNY';

type ProductColor = {
  ar: string;
  en: string;
  hex: string;
  image?: string;
};

type Props = {
  initialProduct: any;
  productId: number;
  canonicalUrl: string;
  categories: any[];
};

function resolveMediaUrl(src: string): string {
  if (!src) return '/assets/women.jpg';
  if (src.startsWith('http://') || src.startsWith('https://')) return src;
  if (src.startsWith('/media/')) {
    return `${getApiBase()}${src}`;
  }
  if (src.startsWith('/')) return src;
  return `/assets/${src}.jpg`;
}

export default function ProductDetailClient({
  initialProduct,
  productId,
  canonicalUrl,
  categories,
}: Props) {
  const [product, setProduct] = useState<any>(initialProduct);
  const [lang, setLang] = useState<'ar' | 'en'>('ar');
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>('ILS');
  const [selectedColorIndex, setSelectedColorIndex] = useState(0);
  const [selectedPhoto, setSelectedPhoto] = useState('');
  const [selectedSize, setSelectedSize] = useState('');
  const [selectedOption, setSelectedOption] = useState('');
  const [qty, setQty] = useState(1);
  const [copied, setCopied] = useState(false);
  const [cartCount, setCartCount] = useState(0);

  const en = lang === 'en';
  const t = (ar: string, english: string) => (en ? english : ar);

  useEffect(() => {
    try {
      const savedLang = localStorage.getItem('algharabli-lang');
      if (savedLang === 'en' || savedLang === 'ar') setLang(savedLang);
      const savedCurr = localStorage.getItem('algharabli-display-currency');
      if (savedCurr === 'CNY' || savedCurr === 'ILS' || savedCurr === 'USD') {
        setDisplayCurrency(savedCurr as DisplayCurrency);
      }
      const rawCart = localStorage.getItem('algharabli-cart');
      if (rawCart) {
        const items = JSON.parse(rawCart);
        if (Array.isArray(items)) {
          setCartCount(items.reduce((acc: number, item: any) => acc + (item.qty || 0), 0));
        }
      }
    } catch {
      // fallback
    }
  }, []);

  useEffect(() => {
    if (product) {
      const minQty = product.min_qty || product.min || 1;
      setQty(minQty);
      if (product.colors && product.colors.length > 0) {
        setSelectedColorIndex(0);
        const color = product.colors[0];
        if (color.image) setSelectedPhoto(resolveMediaUrl(color.image));
        else if (product.image) setSelectedPhoto(resolveMediaUrl(product.image));
      } else if (product.image) {
        setSelectedPhoto(resolveMediaUrl(product.image));
      }

      if (product.sizes && product.sizes.length > 0) {
        setSelectedSize(product.sizes[0]);
      } else if (product.options && product.options.length > 0) {
        setSelectedOption(product.options[0]);
      }
    }
  }, [product]);

  const categoryName = useMemo(() => {
    if (!product || !categories.length) return '';
    const cat = categories.find((c: any) => c.id === product.category_id || c.id === product.category);
    if (!cat) return '';
    return en ? cat.name_en || cat.en : cat.name_ar || cat.ar;
  }, [product, categories, en]);

  const currencySymbol = useMemo(() => {
    switch (displayCurrency) {
      case 'CNY':
        return '¥';
      case 'USD':
        return '$';
      case 'ILS':
      default:
        return '₪';
    }
  }, [displayCurrency]);

  const currentPrice = useMemo(() => {
    if (!product) return 0;
    if (displayCurrency === 'USD' && product.base_price_usd) {
      return Number(product.base_price_usd);
    }
    if (displayCurrency === 'CNY' && product.original_currency === 'CNY' && product.original_price) {
      return Number(product.original_price);
    }
    const val = product.price || product.base_price_ils || product.original_price || 0;
    return Number(val);
  }, [product, displayCurrency]);

  const currentOptionString = useMemo(() => {
    if (!product) return '';
    if (product.colors && product.colors.length > 0 && selectedSize) {
      const color = product.colors[selectedColorIndex];
      if (color) return `${color.name_ar || color.ar} / ${color.name_en || color.en} · ${selectedSize}`;
    }
    return selectedOption || (product.options?.[0] ?? 'افتراضي / Default');
  }, [product, selectedColorIndex, selectedSize, selectedOption]);

  const toggleLanguage = () => {
    const next = lang === 'ar' ? 'en' : 'ar';
    setLang(next);
    try {
      localStorage.setItem('algharabli-lang', next);
    } catch {}
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(canonicalUrl);
      setCopied(true);
      toast.success(t('تم نسخ الرابط بنجاح', 'Link copied to clipboard'));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(t('تعذر نسخ الرابط', 'Failed to copy link'));
    }
  };

  const handleShareWhatsApp = () => {
    if (!product) return;
    const name = en ? product.name_en || product.name_ar : product.name_ar;
    const msg = `${name}\n${currencySymbol}${currentPrice.toFixed(2)}\n\n${canonicalUrl}`;
    const url = `https://wa.me/?text=${encodeURIComponent(msg)}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const handleAddToCart = async () => {
    if (!product) return;
    const minQty = product.min_qty || product.min || 1;
    if (qty < minQty) {
      toast.error(t(`الحد الأدنى للطلب ${minQty}`, `Minimum quantity is ${minQty}`));
      return;
    }

    const key = `${product.id}-${currentOptionString}`;
    try {
      const raw = localStorage.getItem('algharabli-cart');
      const cart: any[] = raw ? JSON.parse(raw) : [];
      const existing = cart.find(x => x.key === key);
      let nextCart: any[];
      if (existing) {
        nextCart = cart.map(x => (x.key === key ? {...x, qty: x.qty + qty} : x));
      } else {
        nextCart = [
          ...cart,
          {
            key,
            id: product.id,
            qty,
            option: currentOptionString,
            price: currentPrice,
          },
        ];
      }
      localStorage.setItem('algharabli-cart', JSON.stringify(nextCart));
      const totalCount = nextCart.reduce((sum, item) => sum + (item.qty || 0), 0);
      setCartCount(totalCount);

      // Best effort backend sync if authenticated session exists
      try {
        await fetch('/api/cart/merge/', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            items: [{product_id: product.id, option: currentOptionString, qty}],
          }),
        });
      } catch {
        // Guest mode or unauthenticated - local storage is authoritative
      }

      toast.success(t('تمت إضافة المنتج إلى السلة', 'Added to your cart'), {
        action: {
          label: t('عرض السلة', 'View cart'),
          onClick: () => {
            window.location.href = '/#cart';
          },
        },
      });
    } catch {
      toast.error(t('حدث خطأ أثناء الإضافة إلى السلة', 'Could not add to cart'));
    }
  };

  if (!product || product.is_archived) {
    return (
      <div dir={en ? 'ltr' : 'rtl'} className="wrap" style={{padding: '80px 20px', textAlign: 'center'}}>
        <h2>{t('المنتج غير متوفر', 'Product Unavailable')}</h2>
        <p style={{margin: '16px 0 24px', color: '#6b7778'}}>
          {t(
            'عذرًا، هذا المنتج غير متوفر في الكتالوج حاليًا أو تمت أرشفته.',
            'Sorry, this product is currently not available in the catalog or has been archived.'
          )}
        </p>
        <Link href="/" className="btn primary">
          {en ? <ArrowLeft size={16} /> : <ArrowRight size={16} />}
          <span>{t('العودة إلى المتجر', 'Back to Store')}</span>
        </Link>
      </div>
    );
  }

  const galleryList = [
    product.image,
    ...(product.gallery || []),
    ...(product.colors?.map((c: any) => c.image).filter(Boolean) || []),
  ]
    .filter(Boolean)
    .map(resolveMediaUrl)
    .filter((v, i, a) => a.indexOf(v) === i);

  const displayPhoto = selectedPhoto || resolveMediaUrl(product.image);

  return (
    <div dir={en ? 'ltr' : 'rtl'} style={{minHeight: '100vh', display: 'flex', flexDirection: 'column'}}>
      {/* Top Header */}
      <header className="site-header" style={{borderBottom: '1px solid #e8e9e6'}}>
        <div className="header-bar wrap" style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0'}}>
          <Link href="/" className="brand" style={{display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none'}}>
            <img src="/favicon.svg" alt="Logo" style={{width: '32px', height: '35px'}} />
            <span>
              <strong>{t('الغرابلي جلوبال', 'Algharabli Global')}</strong>
              <small style={{display: 'block', fontSize: '9px', color: '#5d7278', letterSpacing: '1px'}}>
                {t('لتجارة الجملة', 'WHOLESALE')}
              </small>
            </span>
          </Link>

          <div style={{display: 'flex', alignItems: 'center', gap: '16px'}}>
            <button
              type="button"
              onClick={toggleLanguage}
              className="lang-btn"
              style={{display: 'flex', alignItems: 'center', gap: '6px', background: 'none', border: 'none', cursor: 'pointer', fontSize: '13px'}}
            >
              <Globe2 size={16} />
              <span>{en ? 'العربية' : 'English'}</span>
            </button>

            <Link
              href="/#cart"
              className="cart-btn"
              style={{display: 'flex', alignItems: 'center', gap: '6px', textDecoration: 'none', color: 'inherit'}}
            >
              <ShoppingBag size={20} />
              <span>{t('السلة', 'Cart')}</span>
              <b style={{background: '#b41f71', color: '#fff', borderRadius: '50%', padding: '2px 7px', fontSize: '12px'}}>
                {cartCount}
              </b>
            </Link>
          </div>
        </div>
      </header>

      {/* Breadcrumb & Navigation */}
      <nav className="wrap" style={{padding: '16px 0', fontSize: '13px', color: '#657a79', display: 'flex', alignItems: 'center', gap: '8px'}}>
        <Link href="/" style={{color: '#657a79', display: 'flex', alignItems: 'center', gap: '4px'}}>
          {en ? <ArrowLeft size={14} /> : <ArrowRight size={14} />}
          <span>{t('الكتالوج', 'Catalog')}</span>
        </Link>
        <span>/</span>
        {categoryName && (
          <>
            <span>{categoryName}</span>
            <span>/</span>
          </>
        )}
        <span style={{color: '#2d2730', fontWeight: 'bold'}}>
          {en ? product.name_en || product.name_ar : product.name_ar}
        </span>
      </nav>

      {/* Main Product Container */}
      <main className="wrap" style={{flex: 1, paddingBottom: '60px'}}>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '40px', marginTop: '10px'}}>
          {/* Media / Photos Section */}
          <div>
            <div
              style={{
                borderRadius: '12px',
                overflow: 'hidden',
                background: '#f9f9f9',
                border: '1px solid #e9ece8',
                aspectRatio: '3/4',
                maxHeight: '560px',
                width: '100%',
                position: 'relative',
              }}
            >
              <img
                src={displayPhoto}
                alt={en ? product.name_en || product.name_ar : product.name_ar}
                style={{width: '100%', height: '100%', objectFit: 'cover'}}
              />
              {product.badge && (
                <span
                  style={{
                    position: 'absolute',
                    top: '16px',
                    insetInlineStart: '16px',
                    background: '#b41f71',
                    color: '#fff',
                    padding: '4px 10px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    fontWeight: 'bold',
                  }}
                >
                  {t(product.badge, product.badge)}
                </span>
              )}
            </div>

            {/* Gallery Thumbnails */}
            {galleryList.length > 1 && (
              <div style={{display: 'flex', gap: '10px', marginTop: '12px', flexWrap: 'wrap'}}>
                {galleryList.map((src, idx) => (
                  <button
                    key={src}
                    type="button"
                    onClick={() => setSelectedPhoto(src)}
                    style={{
                      width: '64px',
                      height: '64px',
                      borderRadius: '8px',
                      overflow: 'hidden',
                      border: displayPhoto === src ? '2px solid #b41f71' : '1px solid #dce2df',
                      cursor: 'pointer',
                      padding: 0,
                      background: 'none',
                    }}
                  >
                    <img src={src} alt="" style={{width: '100%', height: '100%', objectFit: 'cover'}} />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Product Details Section */}
          <div style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
            <div>
              {categoryName && (
                <span style={{color: '#9a6e36', fontSize: '13px', fontWeight: 'bold', letterSpacing: '0.5px'}}>
                  {categoryName}
                </span>
              )}
              <h1 style={{fontSize: '28px', fontWeight: '800', margin: '6px 0 10px', color: '#2d2730'}}>
                {en ? product.name_en || product.name_ar : product.name_ar}
              </h1>

              <div style={{display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center', fontSize: '13px', color: '#657a79'}}>
                <span>
                  {t('كود المنتج:', 'Code:')} <bdi style={{fontWeight: 'bold', color: '#2d2730'}}>{product.code}</bdi>
                </span>
                {product.factory_code && (
                  <>
                    <span>•</span>
                    <span>
                      {t('كود المصنع:', 'Factory Code:')}{' '}
                      <bdi style={{fontWeight: 'bold', color: '#2d2730'}}>{product.factory_code}</bdi>
                    </span>
                  </>
                )}
                <span>•</span>
                <span style={{color: product.available ? '#2e7d32' : '#c62828', fontWeight: 'bold'}}>
                  {product.available ? t('متوفر للطلب', 'In Stock') : t('غير متوفر حاليًا', 'Out of Stock')}
                </span>
              </div>
            </div>

            {/* Pricing Section */}
            <div style={{background: '#f8f9fa', padding: '16px 20px', borderRadius: '10px', border: '1px solid #e9ece8'}}>
              <div style={{display: 'flex', alignItems: 'baseline', gap: '8px'}}>
                <span style={{fontSize: '32px', fontWeight: '800', color: '#b41f71'}}>
                  <bdi>
                    {currencySymbol}
                    {currentPrice > 0 ? currentPrice.toFixed(2) : '—'}
                  </bdi>
                </span>
                <span style={{fontSize: '14px', color: '#657a79'}}>
                  {t('لكل', 'per')} {en ? product.unit_en || product.unitEn || 'piece' : product.unit_ar || product.unit || 'قطعة'}
                </span>
              </div>
              <small style={{display: 'block', marginTop: '6px', color: '#6b7778'}}>
                {t('الحد الأدنى للطلب:', 'Minimum Order Quantity:')}{' '}
                <strong>
                  {product.min_qty || product.min || 1}{' '}
                  {en ? product.unit_en || product.unitEn || 'pieces' : product.unit_ar || product.unit || 'قطعة'}
                </strong>
              </small>
            </div>

            {/* Color Swatches */}
            {product.colors && product.colors.length > 0 && (
              <div>
                <label style={{display: 'block', fontSize: '14px', fontWeight: 'bold', marginBottom: '8px', color: '#2d2730'}}>
                  {t('اللون:', 'Color:')}{' '}
                  <span style={{fontWeight: 'normal', color: '#657a79'}}>
                    {en
                      ? product.colors[selectedColorIndex]?.name_en || product.colors[selectedColorIndex]?.en
                      : product.colors[selectedColorIndex]?.name_ar || product.colors[selectedColorIndex]?.ar}
                  </span>
                </label>
                <div style={{display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
                  {product.colors.map((c: any, idx: number) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => {
                        setSelectedColorIndex(idx);
                        if (c.image) setSelectedPhoto(resolveMediaUrl(c.image));
                      }}
                      title={en ? c.name_en || c.en : c.name_ar || c.ar}
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: '50%',
                        backgroundColor: c.hex,
                        border: selectedColorIndex === idx ? '3px solid #b41f71' : '2px solid #fff',
                        boxShadow: '0 0 0 1px #dce2df',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Sizes / Options */}
            {product.sizes && product.sizes.length > 0 && (
              <div>
                <label style={{display: 'block', fontSize: '14px', fontWeight: 'bold', marginBottom: '8px', color: '#2d2730'}}>
                  {t('المقاس:', 'Size:')}
                </label>
                <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap'}}>
                  {product.sizes.map((sz: string) => (
                    <button
                      key={sz}
                      type="button"
                      onClick={() => setSelectedSize(sz)}
                      style={{
                        minWidth: '44px',
                        height: '40px',
                        padding: '0 12px',
                        borderRadius: '6px',
                        border: selectedSize === sz ? '2px solid #b41f71' : '1px solid #dce2df',
                        background: selectedSize === sz ? '#b41f7110' : '#fff',
                        color: selectedSize === sz ? '#b41f71' : '#2d2730',
                        fontWeight: 'bold',
                        cursor: 'pointer',
                      }}
                    >
                      {sz}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Quantity Selector & Add to Cart */}
            <div style={{display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center', marginTop: '10px'}}>
              <div style={{display: 'flex', alignItems: 'center', border: '1px solid #dce2df', borderRadius: '7px', height: '46px'}}>
                <button
                  type="button"
                  disabled={qty <= (product.min_qty || product.min || 1)}
                  onClick={() => setQty(q => Math.max(product.min_qty || product.min || 1, q - 1))}
                  style={{width: '40px', height: '100%', background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center'}}
                  aria-label={t('تقليل الكمية', 'Decrease')}
                >
                  <Minus size={16} />
                </button>
                <input
                  type="number"
                  min={product.min_qty || product.min || 1}
                  value={qty}
                  onChange={e => setQty(Math.max(product.min_qty || product.min || 1, parseInt(e.target.value, 10) || 1))}
                  style={{
                    width: '60px',
                    height: '100%',
                    border: 'none',
                    textAlign: 'center',
                    fontWeight: 'bold',
                    padding: 0,
                    boxShadow: 'none',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setQty(q => q + 1)}
                  style={{width: '40px', height: '100%', background: 'none', border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center'}}
                  aria-label={t('زيادة الكمية', 'Increase')}
                >
                  <Plus size={16} />
                </button>
              </div>

              <button
                type="button"
                className="btn primary"
                disabled={!product.available}
                onClick={handleAddToCart}
                style={{flex: 1, minWidth: '180px', height: '46px'}}
              >
                <ShoppingBag size={18} />
                <span>{t('إضافة إلى السلة', 'Add to Cart')}</span>
              </button>
            </div>

            {/* Share and Deep Linking Actions */}
            <div style={{display: 'flex', gap: '12px', marginTop: '10px', flexWrap: 'wrap'}}>
              <button
                type="button"
                onClick={handleShareWhatsApp}
                className="btn light"
                style={{flex: 1, minWidth: '140px', color: '#128c7e', borderColor: '#25d366'}}
              >
                <Share2 size={16} />
                <span>{t('مشاركة عبر واتساب', 'Share WhatsApp')}</span>
              </button>

              <button
                type="button"
                onClick={handleCopyLink}
                className="btn light"
                style={{flex: 1, minWidth: '140px'}}
              >
                {copied ? <Check size={16} color="#2e7d32" /> : <Copy size={16} />}
                <span>{copied ? t('تم نسخ الرابط', 'Link Copied') : t('نسخ رابط المنتج', 'Copy Link')}</span>
              </button>
            </div>

            {/* Description */}
            {(product.description_ar || product.description_en || product.desc || product.descEn) && (
              <div style={{marginTop: '20px', borderTop: '1px solid #eff0ed', paddingTop: '20px'}}>
                <h3 style={{fontSize: '16px', fontWeight: 'bold', marginBottom: '8px', color: '#2d2730'}}>
                  {t('وصف المنتج', 'Product Description')}
                </h3>
                <p style={{lineHeight: '1.8', color: '#554a52', whiteSpace: 'pre-line'}}>
                  {en
                    ? product.description_en || product.descEn || product.description_ar || product.desc
                    : product.description_ar || product.desc || product.description_en || product.descEn}
                </p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer style={{background: '#142B3B', color: '#fff', padding: '24px 0', marginTop: 'auto'}}>
        <div className="wrap" style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', fontSize: '13px'}}>
          <span>© 2026 {t('الغرابلي جلوبال للتجارة بالجملة', 'Algharabli Global Wholesale')}</span>
          <Link href="/" style={{color: '#fff', textDecoration: 'underline'}}>
            {t('العودة للمتجر الرئيسي', 'Back to Main Store')}
          </Link>
        </div>
      </footer>
    </div>
  );
}
