'use client';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { formatCOP } from '@/lib/api/format';
import { ApiError } from '@/lib/api/problem';
import { useCart } from '@/lib/use-cart';
import { addToCart, closeCart, dismissRemoved, openCart, refreshCart, removeFromCart } from '@/lib/cart';
import { Media } from './media';
import { CustomPieceLink } from './custom-piece-link';
type Props = { locale: Locale; dict: Dictionary; whatsapp?: string | null };
export function CartContents({ locale, dict, whatsapp }: Props) {
  const { cart, loaded, error } = useCart(locale); const t = dict.commerce;
  const [busy, setBusy] = useState<string | null>(null); const [removeError, setRemoveError] = useState(false);
  return <div className="cart-contents"><div aria-live="polite">{!loaded && <p>{t.loading}</p>}{error && <p role="alert">{t.error} <button className="text-link" onClick={() => { void refreshCart(locale).catch(() => {}); }}>{t.retry}</button></p>}{removeError && <p role="alert">{t.removeError}</p>}{cart.removed.map(item => <div className="state-notice" key={item.sku}><p>{item.name} · {item.reason === 'sold' ? t.removed : item.reason === 'preorder' ? t.preorder : t.unavailable}</p><CustomPieceLink locale={locale} dict={dict} whatsapp={whatsapp} /></div>)}{cart.removed.length > 0 && <button className="text-link" onClick={dismissRemoved}>{t.dismiss}</button>}</div>
    {loaded && !cart.items.length ? <div className="empty-state"><h2>{t.empty}</h2><Link className="text-link" href={href('catalog', locale)} onClick={closeCart}>{t.explore} ↗</Link></div> : <>{cart.items.map(item => <article className="cart-line" key={item.sku}>{item.image && <Media image={item.image} sizes="100px" />}<div><Link href={href('piece', locale, item.slug)} onClick={closeCart}><h3>{item.name}</h3></Link><p>{formatCOP(item.effective_price.amount_cents, locale)}</p>{!item.purchasable && <p className="state-notice">{t.reserved}</p>}<button className="text-link" disabled={busy !== null} aria-label={`${t.remove}: ${item.name}`} onClick={async () => { setBusy(item.sku); setRemoveError(false); try { await removeFromCart(locale, item.sku); } catch { setRemoveError(true); } finally { setBusy(null); } }}>{t.remove} ×</button></div></article>)}{cart.items.length > 0 && <><div className="total-line"><span>{t.subtotal}</span><span>{formatCOP(cart.subtotal.amount_cents, locale)}</span></div><p>{t.freeShipping}</p><p className="commerce-note">{t.reservationNote}</p>{cart.items.some(item => item.purchasable) && <Link className="button" href={href('checkout', locale)} onClick={closeCart}>{t.checkout} ↗</Link>}</>}</>}
  </div>;
}
export function CartUtility({ locale, dict, whatsapp }: Props) {
  const { cart, drawer } = useCart(locale); const dialog = useRef<HTMLDialogElement>(null); const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (drawer && !dialog.current?.open) { returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; dialog.current?.showModal(); }
    if (!drawer && dialog.current?.open) dialog.current.close();
  }, [drawer]);
  return <><button aria-label={`${dict.commerce.cart} (${cart.count})`} aria-haspopup="dialog" onClick={openCart}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14l1 14H4L5 7Zm3 0V5a4 4 0 0 1 8 0v2" /></svg><small>{cart.count || ''}</small></button><dialog className="cart-drawer" ref={dialog} aria-labelledby="cart-drawer-title" onCancel={closeCart} onClose={() => { closeCart(); returnFocus.current?.focus(); }}><div className="drawer-heading"><h2 id="cart-drawer-title">{dict.commerce.cart}</h2><button autoFocus aria-label={dict.commerce.close} onClick={closeCart}>×</button></div><CartContents locale={locale} dict={dict} whatsapp={whatsapp} /><Link className="text-link" href={href('cart', locale)} onClick={closeCart}>{dict.commerce.viewCart} ↗</Link></dialog></>;
}
export function AddToCart({ sku, locale, dict, whatsapp }: Props & { sku: string }) {
  const [busy, setBusy] = useState(false); const [code, setCode] = useState(''); const lock = useRef(false); const t = dict.commerce;
  return <div className="add-to-cart"><button className="button" disabled={busy} onClick={async () => { if (lock.current) return; lock.current = true; setBusy(true); setCode(''); try { await addToCart(locale, sku); openCart(); } catch (error) { setCode(error instanceof ApiError ? error.problem.code : 'network'); } finally { lock.current = false; setBusy(false); } }}>{t.add}</button>{code && <div role="alert"><p>{code === 'piece_sold' ? t.removed : code === 'piece_preorder' ? t.preorder : code === 'cart_full' ? t.cartFull : t.error}</p>{code === 'piece_sold' && <CustomPieceLink locale={locale} dict={dict} whatsapp={whatsapp} />}</div>}</div>;
}
