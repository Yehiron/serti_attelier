'use client';
import Link from 'next/link';
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import { clearAttempt, paymentAttemptKey, type Cart, type CartItem, type CreatedOrder, type Order } from '@/lib/commerce';
import type { Settings, WompiCheckout } from '@/lib/api/types';
import { openWompiWidget } from '@/lib/wompi';
import { Checkout } from './checkout';
import { href } from '@/lib/routes';
import { formatCOP } from '@/lib/api/format';
import { ApiError } from '@/lib/api/problem';
import { useCart } from '@/lib/use-cart';
import { browserRequest, addToCart, closeCart, dismissRemoved, openCart, refreshCart, removeFromCart } from '@/lib/cart';
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
function CartSummary({ cart, locale, dict, drawer, onCheckout }: Props & { cart: Cart; drawer: boolean; onCheckout?: () => void }) {
  const t = dict.commerce;
  return <div className="cart-summary"><div className="total-line"><span>{t.subtotal}</span><span>{formatCOP(cart.subtotal.amount_cents, locale)}</span></div>
    <p>{t.freeShipping}</p><p className="commerce-note">{t.reservationNote}</p>
    {cart.items.some(item => item.purchasable) ? (drawer ? <button className="button" onClick={onCheckout}>{t.checkout}</button> : <Link className="button" href={href('checkout', locale)} onClick={closeCart}>{t.checkout} ↗</Link>) : <p className="cart-unavailable">{t.nonePurchasable}</p>}
    {drawer && <button className="cart-continue" onClick={closeCart}>{t.continueExploring}</button>}
  </div>;
}
export function CartContents({ locale, dict, whatsapp, drawer = false, onCheckout }: Props & { drawer?: boolean; onCheckout?: () => void }) {
  const { cart, loaded, error, added } = useCart(locale); const t = dict.commerce;
  const [busy, setBusy] = useState<string | null>(null); const [removeError, setRemoveError] = useState(false);
  return <div className={`cart-contents${drawer ? ' cart-contents-drawer' : ''}`}><div className="cart-list"><div aria-live="polite">{!loaded && <p>{t.loading}</p>}{error && <p role="alert">{t.error} <button className="text-link" onClick={() => { void refreshCart(locale).catch(() => {}); }}>{t.retry}</button></p>}{removeError && <p role="alert">{t.removeError}</p>}{cart.removed.map(item => <div className="state-notice" key={item.sku}><p>{item.name} · {item.reason === 'sold' ? t.removed : item.reason === 'preorder' ? t.preorder : t.unavailable}</p><CustomPieceLink locale={locale} dict={dict} whatsapp={whatsapp} /></div>)}{cart.removed.length > 0 && <button className="text-link" onClick={dismissRemoved}>{t.dismiss}</button>}</div>
    {loaded && !cart.items.length ? <div className="empty-state"><h2>{t.empty}</h2><Link className="text-link cart-explore" href={href('catalog', locale)} onClick={closeCart}>{t.explore} ↗</Link></div> : cart.items.map(item => <CartLine key={item.sku} item={item} locale={locale} dict={dict} added={drawer && added === item.sku} busy={busy === item.sku} disabled={busy !== null} remove={() => { void (async () => { setBusy(item.sku); setRemoveError(false); try { await removeFromCart(locale, item.sku); } catch { setRemoveError(true); } finally { setBusy(null); } })(); }} />)}
    </div>{cart.items.length > 0 && <CartSummary cart={cart} locale={locale} dict={dict} drawer={drawer} onCheckout={onCheckout} />}</div>;
}
export function CartUtility({ locale, dict, whatsapp, settings, monogram }: Props & { settings: Settings; monogram?: string }) {
  const [step, setStep] = useState<'selection' | 'delivery' | 'payment' | 'result'>('selection');
  const [checkoutStep, setCheckoutStep] = useState<'data' | 'delivery' | 'summary'>('data'); const [paying, setPaying] = useState(false);
  const [started, setStarted] = useState(false); const [order, setOrder] = useState<CreatedOrder | null>(null); const [payment, setPayment] = useState<Order | null>(null); const [payBusy, setPayBusy] = useState(false); const [payError, setPayError] = useState(false); const currentCheckout = useRef<WompiCheckout | null>(null); const heading = useRef<HTMLHeadingElement>(null);
  const drawerOpen = useRef(false);
  const t = dict.commerce; const mark = monogram || '/brand/logo/monogram-mark.webp';
  useEffect(() => { if (drawerOpen.current) heading.current?.focus(); }, [step]);
  async function pay(created: CreatedOrder, retry = false) {
    if (payBusy) return; setPayBusy(true); setPayError(false); if (retry) setStep('payment');
    try {
      const element = dialog.current; const scroll = window.scrollY; const bodyHeight = document.body.style.height;
      const checkout = retry ? (await browserRequest<{ wompi: WompiCheckout }>(`orders/${encodeURIComponent(created.public_token)}/payment-attempts`, locale, { method: 'POST', headers: { 'Idempotency-Key': paymentAttemptKey(sessionStorage, created.public_token, payment?.payment.last_attempt?.reference ?? '', () => crypto.randomUUID()) } })).wompi : currentCheckout.current ?? created.wompi;
      if (!checkout) throw new Error('Missing checkout');
      currentCheckout.current = checkout;
      // Wompi's window is absolutely positioned at the top of the document and scrolls with the
      // page: leave the top layer and unlock scrolling while it is open (see body:has(...) in CSS).
      setPaying(true);
      if (element?.open) { element.classList.add('is-paying'); if (element.matches(':modal')) { element.close(); element.show(); } }
      document.body.style.overflow = ''; window.scrollTo(0, 0);
      const restore = () => {
        setPaying(false);
        if (element?.open) { element.classList.remove('is-paying'); if (!element.matches(':modal')) { element.close(); element.showModal(); } }
        document.body.style.overflow = 'hidden'; document.body.style.height = bodyHeight; window.scrollTo(0, scroll);
        heading.current?.focus();
      };
      await openWompiWidget(checkout, result => {
        const id = result?.transaction?.id;
        if (!id) { setPayBusy(false); return; }
        setPayBusy(true);
        // A failed sync is not fatal: the webhook or reconciliation may already have settled it.
        void browserRequest(`orders/${encodeURIComponent(created.public_token)}/payment-sync`, locale, { method: 'POST', body: JSON.stringify({ transaction_id: id }) })
          .catch(() => null)
          .then(() => browserRequest<Order>(`orders/${encodeURIComponent(created.public_token)}`, locale))
          .then(data => { setPayment(data); setStep('result'); if (data.payment.status === 'approved') { try { clearAttempt(sessionStorage); } catch {} void refreshCart(locale).catch(() => {}); } })
          .catch(() => { setPayError(true); setStep('result'); }).finally(() => setPayBusy(false));
      }, restore);
    } catch { setPayError(true); } finally { setPayBusy(false); }
  }
  function created(value: CreatedOrder) { currentCheckout.current = null; setOrder(value); setStep('payment'); if (value.payment_channel === 'manual') { try { clearAttempt(sessionStorage); } catch {} } else void pay(value); }

  const { cart, drawer, focusTarget } = useCart(locale); const dialog = useRef<HTMLDialogElement>(null); const returnFocus = useRef<HTMLElement | null>(null); const previousOverflow = useRef<string | null>(null);
  useEffect(() => () => { if (previousOverflow.current !== null) document.body.style.overflow = previousOverflow.current; }, []);
  useEffect(() => {
    const element = dialog.current; if (!element) return;
    if (drawer) {
      drawerOpen.current = true;
      if (!element.open) { returnFocus.current = focusTarget ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null); element.showModal(); }
      // The piece just added may sit below the fold of a long selection: bring it into view.
      requestAnimationFrame(() => element.querySelector('.cart-line-added')?.scrollIntoView({ block: 'nearest' }));
      if (previousOverflow.current === null) previousOverflow.current = document.body.style.overflow; document.body.style.overflow = paying ? (previousOverflow.current ?? '') : 'hidden';
      element.classList.remove('is-closing');
    }
    else if (element.open) {
      element.classList.add('is-closing');
      const delay = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220;
      const timer = window.setTimeout(() => { element.close(); if (previousOverflow.current !== null) { document.body.style.overflow = previousOverflow.current; previousOverflow.current = null; } returnFocus.current?.focus(); }, delay);
      return () => window.clearTimeout(timer);
    }
  }, [drawer, focusTarget, paying]);
  return <><button aria-label={`${dict.commerce.cart} (${cart.count})`} aria-haspopup="dialog" onClick={() => openCart()}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14l1 14H4L5 7Zm3 0V5a4 4 0 0 1 8 0v2" /></svg><small>{cart.count || ''}</small></button><dialog className={`cart-drawer${paying ? ' is-paying' : ''}`} style={{ '--drawer-mark': `url("${mark.replaceAll('"', '%22')}")` } as CSSProperties} ref={dialog} aria-labelledby="cart-drawer-title" onCancel={event => { event.preventDefault(); closeCart(); }} onKeyDown={event => { if (event.key === 'Escape' && !event.currentTarget.matches(':modal')) closeCart(); }} onClick={event => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeCart(); } }}><div className="drawer-heading"><div><h2 id="cart-drawer-title" tabIndex={-1} ref={step === 'selection' ? heading : undefined}>{dict.commerce.cart}</h2><span>· {cart.count} {cart.count === 1 ? dict.commerce.pieceSingular : dict.commerce.piecePlural}</span></div><button autoFocus aria-label={dict.commerce.close} onClick={closeCart}>×</button></div>
  <div className="drawer-steps">{[t.stepSelection, t.stepData, t.delivery, t.stepPayment].map((label, index) => <span key={label} aria-current={(step === 'selection' ? 0 : step === 'delivery' ? ['data', 'delivery', 'summary'].indexOf(checkoutStep) + 1 : 3) === index ? 'step' : undefined}>{index > 0 && ' · '}{label}</span>)}</div>
  <div hidden={step !== 'selection'} className="drawer-selection"><CartContents locale={locale} dict={dict} whatsapp={whatsapp} drawer onCheckout={() => { setStarted(true); setStep('delivery'); requestAnimationFrame(() => dialog.current?.querySelector<HTMLHeadingElement>('.checkout-details section:not([hidden]) h2')?.focus()); }} /></div>
  {started && <div hidden={step !== 'delivery'} className="drawer-flow"><Checkout locale={locale} dict={dict} settings={settings} onCreated={created} stepped onStepChange={setCheckoutStep} onBack={() => setStep('selection')} /></div>}
  {(step === 'payment' || step === 'result') && order && <div className="drawer-flow" aria-live="polite"><h2 ref={heading} tabIndex={-1}>{step === 'result' ? (payment?.payment.status === 'approved' ? t.approved : payment?.payment.status === 'pending' ? t.confirmingPayment : t.paymentResult) : t.stepPayment}</h2><p>{t.order} · {order.number}</p>{order.payment_channel === 'manual' ? <p className="whitespace-pre-line">{order.manual_instructions}</p> : <>{step === 'payment' && <><p>{t.widgetOpen}</p><p>{t.widgetClosed}</p><button className="button" disabled={payBusy} onClick={() => void pay(order)}>{t.payWompi}</button></>}{step === 'result' && <>{payment?.payment.status === 'approved' ? <><div className="drawer-result-mark" aria-hidden="true" /><p>{t.confirmationEmail}</p></> : payment?.payment.status === 'pending' ? <p>{t.confirmingPayment}</p> : <><p>{t.paymentIncomplete}</p><button className="button" disabled={payBusy} onClick={() => void pay(order, true)}>{t.retry}</button></>}</>}{payError && <p role="alert">{t.syncDelayed}</p>}<p className="drawer-trust"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 10V7a6 6 0 0 1 12 0v3M5 10h14v11H5z" /></svg>{t.wompiSecure}</p></>}<p><Link className="text-link" href={href('order', locale, order.public_token)} onClick={closeCart}>{t.viewOrder} ↗</Link></p></div>}</dialog></>;
}
export function AddToCart({ sku, locale, dict, whatsapp }: Props & { sku: string }) {
  const [busy, setBusy] = useState(false); const [code, setCode] = useState(''); const lock = useRef(false); const button = useRef<HTMLButtonElement>(null); const t = dict.commerce;
  return <div className="add-to-cart"><button ref={button} className="button" disabled={busy} onClick={async () => { if (lock.current) return; lock.current = true; setBusy(true); setCode(''); try { await addToCart(locale, sku); openCart({ added: sku, focusTarget: button.current }); } catch (error) { setCode(error instanceof ApiError ? error.problem.code : 'network'); } finally { lock.current = false; setBusy(false); } }}>{t.add}</button>{code && <div role="alert"><p>{code === 'piece_sold' ? t.removed : code === 'piece_preorder' ? t.preorder : code === 'cart_full' ? t.cartFull : t.error}</p>{code === 'piece_sold' && <CustomPieceLink locale={locale} dict={dict} whatsapp={whatsapp} />}</div>}</div>;
}
