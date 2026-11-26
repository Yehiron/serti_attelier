'use client';
import Link from 'next/link';
import type { BrandIdentity } from '@/lib/cms-brand';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode, Fragment } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { CmsMenuItem, Taxonomy, Settings } from '@/lib/api/types';
import { href, routeDecision } from '@/lib/routes';
import { useWishlist } from '@/lib/use-wishlist';
import { CartUtility } from './cart';
import { BrandLogo, Wordmark } from './media';
import { Heart } from './heart';
import { Flag } from './flag';
import { QuickSearch } from './quick-search';
export function Navigation({ locale, dict, taxonomy, whatsapp, items, brand, settings }: { settings: Settings; brand?: BrandIdentity; locale: Locale; dict: Dictionary; taxonomy: Taxonomy; whatsapp?: string | null; items?: CmsMenuItem[] }) {
  const routePathname = usePathname();
  // Normalize both the SSR internal path and the public browser path identically.
  const decision = routeDecision(routePathname);
  const pathname = decision.kind === 'redirect' ? decision.pathname : routePathname;
  const dialog = useRef<HTMLDialogElement>(null);
  const desktopNav = useRef<HTMLElement>(null);
  // One shared value: opening a menu closes any other one.
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const [alternate, setAlternate] = useState(href('home', locale === 'es' ? 'en' : 'es'));
  const { wishes } = useWishlist();
  const home = routePathname === `/${locale}`;
  useEffect(() => {
    const scroll = () => setScrolled(window.scrollY > 40);
    scroll(); window.addEventListener('scroll', scroll, { passive: true });
    return () => window.removeEventListener('scroll', scroll);
  }, []);
  useEffect(() => {
    const update = () => {
      const other = locale === 'es' ? 'en' : 'es';
      const marker = document.querySelector<HTMLElement>('[data-alternate-es]');
      setAlternate(marker?.dataset[other === 'es' ? 'alternateEs' : 'alternateEn'] ?? href('home', other));
    };
    update(); const observer = new MutationObserver(update); observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-alternate-es', 'data-alternate-en'] });
    return () => observer.disconnect();
  }, [pathname, locale]);
  // Navigating closes the open menu (state adjusted during render, not in an effect).
  const [menuPath, setMenuPath] = useState(routePathname);
  if (menuPath !== routePathname) { setMenuPath(routePathname); setOpenMenu(null); }
  useEffect(() => {
    if (!openMenu) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!desktopNav.current?.contains(target) && !dialog.current?.contains(target)) setOpenMenu(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || dialog.current?.open) return;
      desktopNav.current?.querySelector<HTMLElement>(`[data-menu="${openMenu}"] > summary`)?.focus();
      setOpenMenu(null);
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [openMenu]);
  const menu = (key: string, label: string, children: ReactNode) => <details data-menu={key} open={openMenu === key}>
    <summary onClick={event => { event.preventDefault(); setOpenMenu(value => value === key ? null : key); }}>{label}</summary>
    <div>{children}</div>
  </details>;
  const current = (url: string) => pathname === url ? 'page' as const : undefined;
  const menuItems: CmsMenuItem[] = items ?? [
    { label: dict.nav.catalog, href: href('catalog', locale), external: false, dropdown: 'catalog' },
    { label: dict.nav.stones, href: '', external: false, dropdown: 'stones' },
    { label: dict.nav.collections, href: '', external: false, dropdown: 'collections' },
    ...(['personalize', 'story', 'contact'] as const).map(key => ({ label: dict.nav[key], href: href(key, locale), external: false, dropdown: null })),
  ];
  const links = <>{menuItems.map((item, index) => <Fragment key={`${item.dropdown ?? item.href}-${index}`}>
    {item.dropdown === 'catalog' ? menu('catalog', item.label, <><Link prefetch={true} href={href('catalog', locale)} aria-current={current(href('catalog', locale))}>{dict.ui.all}</Link>{taxonomy.categories.map(x => <div key={x.slug}><Link prefetch={true} href={href('category', locale, x.slug)} aria-current={current(href('category', locale, x.slug))}>{x.name}</Link>{x.children.map(child => <Link prefetch={true} className="subcategory" key={child.slug} href={href('category', locale, child.slug)} aria-current={current(href('category', locale, child.slug))}>{child.name}</Link>)}</div>)}</>)
      : item.dropdown === 'stones' ? menu('stones', item.label, taxonomy.stones.map(x => <Link prefetch={true} key={x.slug} href={href('stone', locale, x.slug)} aria-current={current(href('stone', locale, x.slug))}>{x.name}</Link>))
      : item.dropdown === 'collections' ? menu('collections', item.label, taxonomy.collections.map(x => <Link prefetch={true} key={x.slug} href={href('collection', locale, x.slug)} aria-current={current(href('collection', locale, x.slug))}>{x.name}</Link>))
      : item.external ? <a href={item.href} target="_blank" rel="noopener noreferrer">{item.label}</a>
      : <Link prefetch={true} href={item.href} aria-current={current(item.href)}>{item.label}</Link>}
  </Fragment>)}</>;
  return <header className={`site-header ${home && !scrolled ? 'over-hero' : ''}`}>
    <Link prefetch={true} className="brand-link" href={href('home', locale)} aria-label={`SERTI · ${dict.nav.home}`} onClick={event => {
      // Already on the home page the route doesn't change: bring the visitor back to the top.
      if (pathname !== href('home', locale) || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      window.scrollTo({ top: 0, behavior: reduce ? 'instant' : 'smooth' });
    }}><BrandLogo brand={brand} /></Link>
    <nav ref={desktopNav} className="desktop-nav" aria-label={dict.nav.menu}>{links}</nav>
    <div className="utilities">{process.env.NEXT_PUBLIC_CART_ENABLED === 'true' && <CartUtility locale={locale} dict={dict} whatsapp={whatsapp} settings={settings} monogram={brand?.monogram_dark?.src || brand?.monogram_light?.src} />}<QuickSearch locale={locale} dict={dict} taxonomy={taxonomy} /><Link className="wishlist-utility" href={href('wishlist', locale)} aria-label={`${dict.nav.wishlist} (${wishes.length})`}><Heart filled={wishes.length > 0} /><small>{wishes.length || ''}</small></Link><a href={alternate} hrefLang={locale === 'es' ? 'en' : 'es'} className="lang-link" aria-label={`${locale.toUpperCase()} · ${dict.nav.language}: ${dict.nav.otherLanguage}`}><Flag locale={locale} />{locale.toUpperCase()}</a><button className="menu-trigger" onClick={() => dialog.current?.showModal()} aria-label={dict.nav.menu}>☰</button></div>
    <dialog ref={dialog} className="menu-dialog" aria-label={dict.nav.menu} onClose={() => setOpenMenu(null)} onClick={event => { if ((event.target as HTMLElement).closest('a')) dialog.current?.close(); }}><div className="menu-top"><Wordmark brand={brand} /><button onClick={() => dialog.current?.close()}>{dict.nav.close} ×</button></div><nav aria-label={dict.nav.menu}>{links}</nav><a className="lang-link" href={alternate}><Flag locale={locale} />{locale.toUpperCase()} · {dict.nav.otherLanguage}</a></dialog>
  </header>;
}
