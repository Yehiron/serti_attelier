'use client';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { Cart, CartItem } from '@/lib/commerce';
import { href } from '@/lib/routes';
import { formatCOP } from '@/lib/api/format';
import { ApiError } from '@/lib/api/problem';
import { useCart } from '@/lib/use-cart';
import { addToCart, closeCart, dismissRemoved, openCart, refreshCart, removeFromCart } from '@/lib/cart';
import { Media } from './media';
import { CustomPieceLink } from './custom-piece-link';
type Props = { locale: Locale; dict: Dictionary; whatsapp?: string | null };

function CartLine({ item, locale, dict, added, busy, disabled, remove }: Props & { item: CartItem; added: boolean; busy: boolean; disabled: boolean; remove: () => void }) {
  const t = dict.commerce;
  return <article className={`cart-line${added ? ' cart-line-added' : ''}${!item.purchasable ? ' cart-line-unavailable' : ''}`}>
    {item.image && <Media image={item.image} sizes="100px" />}
    <div><div aria-live="polite">{added && <p className="cart-added">{t.added}</p>}</div><Link href={href('piece', locale, item.slug)} onClick={closeCart}><h3>{item.name}</h3></Link>
      <p className="cart-price">{item.sale_price && <del>{formatCOP(item.price.amount_cents, locale)} </del>}{formatCOP(item.effective_price.amount_cents, locale)}</p>
      {!item.purchasable && <p className="cart-unavailable">{t.reserved}</p>}
      <button className="text-link cart-remove" disabled={disabled} aria-label={`${t.remove}: ${item.name}`} onClick={remove}>{busy ? t.removing : t.remove} ×</button>
    </div>
  </article>;
}
function CartSummary({ cart, locale, dict, drawer }: Props & { cart: Cart; drawer: boolean }) {
  const t = dict.commerce;
  return <div className="cart-summary"><div className="total-line"><span>{t.subtotal}</span><span>{formatCOP(cart.subtotal.amount_cents, locale)}</span></div>
    <p>{t.freeShipping}</p><p className="commerce-note">{t.reservationNote}</p>
    {cart.items.some(item => item.purchasable) ? <Link className="button" href={href('checkout', locale)} onClick={closeCart}>{t.checkout} ↗</Link> : <p className="cart-unavailable">{t.nonePurchasable}</p>}
    {drawer && <button className="cart-continue" onClick={closeCart}>{t.continueExploring}</button>}
  </div>;
}
export function CartContents({ locale, dict, whatsapp, drawer = false }: Props & { drawer?: boolean }) {
  const { cart, loaded, error, added } = useCart(locale); const t = dict.commerce;
  const [busy, setBusy] = useState<string | null>(null); const [removeError, setRemoveError] = useState(false);
  return <div className={`cart-contents${drawer ? ' cart-contents-drawer' : ''}`}><div className="cart-list"><div aria-live="polite">{!loaded && <p>{t.loading}</p>}{error && <p role="alert">{t.error} <button className="text-link" onClick={() => { void refreshCart(locale).catch(() => {}); }}>{t.retry}</button></p>}{removeError && <p role="alert">{t.removeError}</p>}{cart.removed.map(item => <div className="state-notice" key={item.sku}><p>{item.name} · {item.reason === 'sold' ? t.removed : item.reason === 'preorder' ? t.preorder : t.unavailable}</p><CustomPieceLink locale={locale} dict={dict} whatsapp={whatsapp} /></div>)}{cart.removed.length > 0 && <button className="text-link" onClick={dismissRemoved}>{t.dismiss}</button>}</div>
    {loaded && !cart.items.length ? <div className="empty-state"><h2>{t.empty}</h2><Link className="text-link cart-explore" href={href('catalog', locale)} onClick={closeCart}>{t.explore} ↗</Link></div> : cart.items.map(item => <CartLine key={item.sku} item={item} locale={locale} dict={dict} added={drawer && added === item.sku} busy={busy === item.sku} disabled={busy !== null} remove={() => { void (async () => { setBusy(item.sku); setRemoveError(false); try { await removeFromCart(locale, item.sku); } catch { setRemoveError(true); } finally { setBusy(null); } })(); }} />)}
    </div>{cart.items.length > 0 && <CartSummary cart={cart} locale={locale} dict={dict} drawer={drawer} />}</div>;
}
export function CartUtility({ locale, dict, whatsapp }: Props) {
  const { cart, drawer, focusTarget } = useCart(locale); const dialog = useRef<HTMLDialogElement>(null); const returnFocus = useRef<HTMLElement | null>(null); const previousOverflow = useRef<string | null>(null);
  useEffect(() => () => { if (previousOverflow.current !== null) document.body.style.overflow = previousOverflow.current; }, []);
  useEffect(() => {
    const element = dialog.current; if (!element) return;
    if (drawer) {
      if (!element.open) { returnFocus.current = focusTarget ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null); element.showModal(); }
      // The piece just added may sit below the fold of a long selection: bring it into view.
      requestAnimationFrame(() => element.querySelector('.cart-line-added')?.scrollIntoView({ block: 'nearest' }));
      if (previousOverflow.current === null) previousOverflow.current = document.body.style.overflow; document.body.style.overflow = 'hidden';
      element.classList.remove('is-closing');
    }
    else if (element.open) {
      element.classList.add('is-closing');
      const delay = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220;
      const timer = window.setTimeout(() => { element.close(); if (previousOverflow.current !== null) { document.body.style.overflow = previousOverflow.current; previousOverflow.current = null; } returnFocus.current?.focus(); }, delay);
      return () => window.clearTimeout(timer);
    }
  }, [drawer, focusTarget]);
  return <><button aria-label={`${dict.commerce.cart} (${cart.count})`} aria-haspopup="dialog" onClick={() => openCart()}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14l1 14H4L5 7Zm3 0V5a4 4 0 0 1 8 0v2" /></svg><small>{cart.count || ''}</small></button><dialog className="cart-drawer" ref={dialog} aria-labelledby="cart-drawer-title" onCancel={event => { event.preventDefault(); closeCart(); }} onClick={event => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeCart(); } }}><div className="drawer-heading"><div><h2 id="cart-drawer-title">{dict.commerce.cart}</h2><span>· {cart.count} {cart.count === 1 ? dict.commerce.pieceSingular : dict.commerce.piecePlural}</span></div><button autoFocus aria-label={dict.commerce.close} onClick={closeCart}>×</button></div><CartContents locale={locale} dict={dict} whatsapp={whatsapp} drawer /></dialog></>;
}
export function AddToCart({ sku, locale, dict, whatsapp }: Props & { sku: string }) {
  const [busy, setBusy] = useState(false); const [code, setCode] = useState(''); const lock = useRef(false); const button = useRef<HTMLButtonElement>(null); const t = dict.commerce;
  return <div className="add-to-cart"><button ref={button} className="button" disabled={busy} onClick={async () => { if (lock.current) return; lock.current = true; setBusy(true); setCode(''); try { await addToCart(locale, sku); openCart({ added: sku, focusTarget: button.current }); } catch (error) { setCode(error instanceof ApiError ? error.problem.code : 'network'); } finally { lock.current = false; setBusy(false); } }}>{t.add}</button>{code && <div role="alert"><p>{code === 'piece_sold' ? t.removed : code === 'piece_preorder' ? t.preorder : code === 'cart_full' ? t.cartFull : t.error}</p>{code === 'piece_sold' && <CustomPieceLink locale={locale} dict={dict} whatsapp={whatsapp} />}</div>}</div>;
}
