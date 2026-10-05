'use client';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {ChevronDown,Globe2,Menu,ShoppingBag,UserRound,X} from 'lucide-react';
import {Sheet,SheetContent,SheetTitle,SheetDescription,SheetTrigger,SheetClose} from '@/components/ui/sheet';
import {catalogHref,type CatalogGroup} from './catalog-navigation';

type Props={lang:'ar'|'en';page:string;category:number;subcategory:string;groups:CatalogGroup[];logo:ReactNode;accountLabel:string;cartCount:number;onLanguage:()=>void;onAccount:()=>void;onNavigate:(page:string)=>void;onCatalog:(category?:number,subcategory?:string)=>void};
export default function StoreHeader({lang,page,category,subcategory,groups,logo,accountLabel,cartCount,onLanguage,onAccount,onNavigate,onCatalog}:Props){
  const en=lang==='en';const t=(ar:string,eng:string)=>en?eng:ar;
  const [mega,setMega]=useState(false);const [mobile,setMobile]=useState(false);
  const area=useRef<HTMLDivElement>(null);const trigger=useRef<HTMLButtonElement>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);const focusFirst=useRef(false);
  const cancel=()=>{if(timer.current)clearTimeout(timer.current);timer.current=null};
  const close=()=>{cancel();setMega(false)};
  const navigate=(next:string)=>{close();setMobile(false);onNavigate(next)};
  const catalog=(id=0,sub='')=>{close();setMobile(false);onCatalog(id,sub)};
  useEffect(()=>{close();setMobile(false)},[page,category,subcategory]);
  useEffect(()=>()=>cancel(),[]);
  useEffect(()=>{
    if(!mega)return;
    if(focusFirst.current){area.current?.querySelector<HTMLAnchorElement>('.mega-panel a')?.focus();focusFirst.current=false}
    const outside=(e:PointerEvent)=>{if(!area.current?.contains(e.target as Node))close()};
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();close();trigger.current?.focus()}};
    document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);
    return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)};
  },[mega]);
  const routes=[{id:'home',ar:'الرئيسية',en:'Home'},{id:'traders',ar:'التجار',en:'Traders'},{id:'export',ar:'التصدير',en:'Export'},{id:'info',ar:'من نحن',en:'About us'},{id:'contact',ar:'تواصل معنا',en:'Contact us'}];
  const pageLink=(route:typeof routes[number],mobileLink=false)=><a key={route.id} href={'#'+route.id} className={page===route.id?(mobileLink?'active':'nav-active'):''} aria-current={page===route.id?'page':undefined} onClick={e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();navigate(route.id)}}>{en?route.en:route.ar}</a>;
  const catalogLink=(id:number,sub:string,label:string,className='')=><a href={catalogHref(id,sub)} className={className} aria-current={page==='products'&&category===id&&subcategory===sub?'page':undefined} onClick={e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();catalog(id,sub)}}>{label}</a>;
  return <Sheet open={mobile} onOpenChange={setMobile}>
    <header className={'site-header organized-header '+(page==='home'?'home-header':'')}>
      <div className="header-bar wrap">
        <a className="brand-button" href="#home" aria-label={t('رواق — الرئيسية','Riwaq — Home')} onClick={e=>{e.preventDefault();navigate('home')}}>{logo}</a>
        <nav className="nav-links" aria-label={t('التنقل الرئيسي','Main navigation')}>
          {pageLink(routes[0])}
          <div className="catalog-disclosure" ref={area} onMouseEnter={()=>{if(window.matchMedia('(hover:hover)').matches){cancel();setMega(true)}}} onMouseLeave={()=>{cancel();timer.current=setTimeout(()=>{const focused=document.activeElement;if(focused!==trigger.current&&area.current?.contains(focused))return;setMega(false)},200)}} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))close()}}>
            <button ref={trigger} type="button" className={'catalog-trigger '+(page==='products'?'nav-active':'')} aria-expanded={mega} aria-controls="catalog-mega-panel" onClick={()=>{cancel();setMega(v=>!v)}} onKeyDown={e=>{if(e.key==='ArrowDown'){e.preventDefault();cancel();focusFirst.current=true;if(mega){area.current?.querySelector<HTMLAnchorElement>('.mega-panel a')?.focus();focusFirst.current=false}else setMega(true)}}}>{t('الكتالوج','Catalog')}<ChevronDown size={15} className={mega?'expanded':''}/></button>
            {mega&&<div id="catalog-mega-panel" className="mega-panel" aria-label={t('أقسام الكتالوج','Catalog categories')} onMouseEnter={cancel}>
              <div className="mega-top"><strong>{t('تسوّق حسب القسم','Shop by category')}</strong>{catalogLink(0,'',t('عرض الكتالوج كاملًا','View the full catalog'),'mega-all')}</div>
              <div className="mega-grid">{groups.map(group=><section className="mega-column" key={group.id}>{catalogLink(group.id,'',en?group.en:group.ar,'mega-category')}<span className="mega-count">{group.count} {t('منتجات','products')}</span><ul>{group.children.map(child=><li key={child.id}>{catalogLink(group.id,child.id,en?child.en:child.ar)}<span>{child.count}</span></li>)}</ul></section>)}</div>
            </div>}
          </div>
          {routes.slice(1).map(route=>pageLink(route))}
        </nav>
        <div className="header-actions"><button className="lang-btn" type="button" onClick={onLanguage} aria-label={t('التبديل إلى الإنجليزية','Switch to Arabic')}><Globe2 size={18}/><span>{en?'العربية':'English'}</span></button><span className="divider"/><button className="account-btn" type="button" onClick={onAccount}><UserRound size={20}/><span>{accountLabel}</span></button><button className="cart-btn" type="button" onClick={()=>navigate('cart')} aria-label={t('السلة','Cart')}><ShoppingBag size={20}/><span>{t('السلة','Cart')}</span><b>{cartCount}</b></button><SheetTrigger asChild><button type="button" className="mobile-menu-trigger" aria-label={t('فتح القائمة','Open menu')} aria-controls="mobile-store-menu"><Menu size={21}/></button></SheetTrigger></div>
      </div>
    </header>
    <SheetContent id="mobile-store-menu" side="left" showCloseButton={false} className="mobile-store-sheet organized-mobile" dir={en?'ltr':'rtl'}>
      <div className="mobile-menu-heading"><SheetTitle>{t('قائمة رواق','Riwaq menu')}</SheetTitle><SheetClose asChild><button type="button" aria-label={t('إغلاق القائمة','Close menu')}><X size={21}/></button></SheetClose></div>
      <SheetDescription className="sr-only">{t('الصفحات الأساسية وأقسام الكتالوج','Main pages and catalog categories')}</SheetDescription>
      <nav className="mobile-menu-links" aria-label={t('التنقل الرئيسي','Main navigation')}>
        {pageLink(routes[0],true)}
        <details className="mobile-catalog" key={page==='products'?'catalog-active':'catalog'} open={page==='products'||undefined}><summary>{t('الكتالوج','Catalog')}<ChevronDown size={18}/></summary><div className="mobile-catalog-body">{catalogLink(0,'',t('عرض الكتالوج كاملًا','View the full catalog'),'mobile-all')}{groups.map(group=><details className="mobile-category" key={group.id} open={category===group.id||undefined}><summary>{en?group.en:group.ar}<ChevronDown size={16}/></summary><div>{catalogLink(group.id,'',t('عرض جميع منتجات القسم','View all in this category'),'mobile-category-all')}{group.children.map(child=><div key={child.id}>{catalogLink(group.id,child.id,en?child.en:child.ar)}</div>)}</div></details>)}</div></details>
        {routes.slice(1).map(route=>pageLink(route,true))}
        <span className="mobile-menu-label">{t('حسابك وطلباتك','Your account & orders')}</span><button type="button" onClick={()=>{setMobile(false);onAccount()}}>{accountLabel}</button><button type="button" onClick={()=>navigate('cart')}>{t('سلة الطلب','Order cart')}<bdi className="mobile-cart-count">{cartCount}</bdi></button><a href="#info" onClick={e=>{e.preventDefault();navigate('info')}}>{t('معلومات الطلب والأسئلة الشائعة','Ordering information & FAQ')}</a>
      </nav>
      <button type="button" className="mobile-menu-language" onClick={onLanguage}><Globe2 size={18}/>{en?'العربية':'English'}</button>
    </SheetContent>
  </Sheet>;
}
