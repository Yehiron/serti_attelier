'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { Taxonomy } from '@/lib/api/types';
import { href, routeDecision } from '@/lib/routes';
import { useWishlist } from '@/lib/use-wishlist';
import { CartUtility } from './cart';
import { Monogram } from './media';
export function Navigation({ locale, dict, taxonomy, whatsapp }: { locale: Locale; dict: Dictionary; taxonomy: Taxonomy; whatsapp?: string | null }) {
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
  const links = <>
    {menu('catalog', dict.nav.catalog, <><Link href={href('catalog', locale)} aria-current={current(href('catalog', locale))}>{dict.ui.all}</Link>{taxonomy.categories.map(x => <div key={x.slug}><Link href={href('category', locale, x.slug)} aria-current={current(href('category', locale, x.slug))}>{x.name}</Link>{x.children.map(child => <Link className="subcategory" key={child.slug} href={href('category', locale, child.slug)} aria-current={current(href('category', locale, child.slug))}>{child.name}</Link>)}</div>)}</>)}
    {menu('stones', dict.nav.stones, taxonomy.stones.map(x => <Link key={x.slug} href={href('stone', locale, x.slug)} aria-current={current(href('stone', locale, x.slug))}>{x.name}</Link>))}
    {menu('collections', dict.nav.collections, taxonomy.collections.map(x => <Link key={x.slug} href={href('collection', locale, x.slug)} aria-current={current(href('collection', locale, x.slug))}>{x.name}</Link>))}
    {(['personalize', 'story', 'contact'] as const).map(key => <Link key={key} href={href(key, locale)} aria-current={current(href(key, locale))}>{dict.nav[key]}</Link>)}
  </>;
  return <header className={`site-header ${home && !scrolled ? 'over-hero' : ''}`}>
    <Link className="brand-link" href={href('home', locale)} aria-label={`SERTI · ${dict.nav.home}`}><Monogram /></Link>
    <nav ref={desktopNav} className="desktop-nav" aria-label={dict.nav.menu}>{links}</nav>
    <div className="utilities">{process.env.NEXT_PUBLIC_CART_ENABLED === 'true' && <CartUtility locale={locale} dict={dict} whatsapp={whatsapp} />}<Link href={href('search', locale)} aria-label={dict.nav.search}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/></svg></Link><Link className="wishlist-utility" href={href('wishlist', locale)} aria-label={`${dict.nav.wishlist} (${wishes.length})`}>♡<small>{wishes.length || ''}</small></Link><a href={alternate} hrefLang={locale === 'es' ? 'en' : 'es'} aria-label={dict.nav.language}>{locale === 'es' ? 'EN' : 'ES'}</a><button className="menu-trigger" onClick={() => dialog.current?.showModal()} aria-label={dict.nav.menu}>☰</button></div>
    <dialog ref={dialog} className="menu-dialog" aria-label={dict.nav.menu} onClose={() => setOpenMenu(null)} onClick={event => { if ((event.target as HTMLElement).closest('a')) dialog.current?.close(); }}><div className="menu-top"><Monogram /><button onClick={() => dialog.current?.close()}>{dict.nav.close} ×</button></div><nav aria-label={dict.nav.menu}>{links}</nav><a href={alternate}>{dict.nav.otherLanguage}</a></dialog>
  </header>;
}
