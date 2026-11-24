'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Settings } from '@/lib/api/types';
import type { Locale } from '@/lib/i18n';
import { formatCOP } from '@/lib/api/format';
import { ApiError } from '@/lib/api/problem';
import { browserRequest, refreshCart } from '@/lib/cart';
import { useCart } from '@/lib/use-cart';
import { attemptStorageKey, checkoutAttempt, checkoutPayload, clearAttempt, couponMessageKey, quoteEmail, fieldErrors, readAttempt, rememberAttemptOrder, type Attempt, type CreatedOrder, type Quote } from '@/lib/commerce';
import { openWompiWidget } from '@/lib/wompi';
import { href } from '@/lib/routes';
import { CustomPieceLink } from './custom-piece-link';
import { Media } from './media';
import { validateCheckoutFields } from '@/lib/checkout-validation';
import { Totals } from './commerce-totals';
export type CommerceProps = { locale: Locale; dict: Dictionary; settings: Settings };
type Step = 'data' | 'delivery' | 'summary';
type Location = { code: string; name: string };
export function Checkout({ locale, dict, settings: initialSettings, onCreated, stepped = false, onStepChange, onBack }: CommerceProps & { onCreated?: (order: CreatedOrder) => void; stepped?: boolean; onStepChange?: (step: Step) => void; onBack?: () => void }) {
  const t = dict.commerce; const router = useRouter(); const { cart, loaded, error: cartError } = useCart(locale);
  const [settings, setSettings] = useState(initialSettings); const [departments, setDepartments] = useState<Location[]>([]); const [municipalities, setMunicipalities] = useState<Location[]>([]); const [department, setDepartment] = useState(''); const [locationError, setLocationError] = useState(false); const [locationRetry, setLocationRetry] = useState(0);
  const [email, setEmail] = useState(''); const [couponInput, setCouponInput] = useState(''); const [coupon, setCoupon] = useState(''); const [certificate, setCertificate] = useState(false); const [channel, setChannel] = useState<'wompi' | 'manual'>('wompi');
  const [quoteResult, setQuoteResult] = useState<{ data: Quote; signature: string } | null>(null); const [quoteError, setQuoteError] = useState(false); const [quoteRetry, setQuoteRetry] = useState(0);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const [errors, setErrors] = useState<Record<string, string[]>>({}); const [conflict, setConflict] = useState(false); const [pending, setPending] = useState<Attempt | null>(null); const [recovered, setRecovered] = useState(false);
  const [step, setStep] = useState<Step>('data'); const stepHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { if (stepped && recovered && loaded) requestAnimationFrame(() => stepHeading.current?.focus()); }, [stepped, recovered, loaded]);
  function goStep(next: Step) { setStep(next); onStepChange?.(next); requestAnimationFrame(() => stepHeading.current?.focus()); }
  const form = useRef<HTMLFormElement>(null); const summary = useRef<HTMLDivElement>(null); const lock = useRef(false);
  const signature = JSON.stringify([cart.items, coupon, certificate, coupon ? email : ""]); const quote = quoteResult?.signature === signature ? quoteResult.data : null;
  useEffect(() => {
    // Read after hydration; the persisted attempt can be replayed even if its cart was emptied.
    void Promise.resolve().then(() => { try { setPending(readAttempt(sessionStorage)); } catch { /* Storage is checked again before submitting. */ } setRecovered(true); });
    void browserRequest<Settings>('site/settings', locale).then(setSettings).catch(() => {});
  }, [locale]);
  useEffect(() => {
    const controller = new AbortController();
    void browserRequest<Location[]>('locations/departments', locale, { signal: controller.signal }).then(data => { setDepartments(data); setLocationError(false); }).catch(() => { if (!controller.signal.aborted) setLocationError(true); });
    return () => controller.abort();
  }, [locale, locationRetry]);
  useEffect(() => {
    if (!department) return;
    const controller = new AbortController();
    void browserRequest<Location[]>(`locations/departments/${encodeURIComponent(department)}/municipalities`, locale, { signal: controller.signal }).then(data => { setMunicipalities(data); setLocationError(false); }).catch(() => { if (!controller.signal.aborted) setLocationError(true); });
    return () => controller.abort();
  }, [department, locale, locationRetry]);
  useEffect(() => {
    if (!loaded || !cart.items.length) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void browserRequest<Quote>('checkout/quote', locale, { method: 'POST', body: JSON.stringify({ coupon_code: coupon, wants_certificate: certificate, email: coupon ? quoteEmail(email) : undefined }), signal: controller.signal }).then(data => { setQuoteResult({ data, signature }); setQuoteError(false); setChannel(previous => data.payment_channels.includes(previous) ? previous : data.payment_channels[0] ?? 'wompi'); }).catch(() => { if (!controller.signal.aborted) setQuoteError(true); });
    }, 350);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [signature, loaded, cart.items.length, coupon, certificate, email, locale, quoteRetry]);
  function fail(text: string, fields: Record<string, string[]> = {}) { if (stepped) { const keys = Object.keys(fields); if (keys.some(key => key.startsWith('contact.'))) goStep('data'); else if (keys.some(key => key.startsWith('shipping.'))) goStep('delivery'); } setMessage(text); setErrors(fields); requestAnimationFrame(() => summary.current?.focus()); }
  const legalReady = !!settings.legal_versions?.terms && !!settings.legal_versions?.privacy && ['terms','privacy'].every(kind => settings.legal_pages.some(page => page.kind === kind));
  async function submit() {
    if (lock.current) return;
    setConflict(false); setErrors({}); setMessage('');
    // An attempt whose order already exists is not replayed: a new checkout starts fresh.
    const replay = pending && !pending.order ? pending : null;
    if (!replay) {
      if (!form.current || !quote || !legalReady) { fail(t.legalUnavailable); return; }
      const fields = validateCheckoutFields(new FormData(form.current), ['data', 'delivery', 'summary'], t);
      if (Object.keys(fields).length) { fail(t.reviewErrors, fields); return; }
      if (!quote.payment_channels.includes(channel)) { fail(t.paymentUnavailable); return; }
    }
    lock.current = true; setBusy(true);
    let attempt: Attempt | null = null; let navigating = false;
    try {
      const body = checkoutPayload(new FormData(form.current!), { coupon, certificate, channel, terms: settings.legal_versions?.terms ?? null, privacy: settings.legal_versions?.privacy ?? null, locale });
      // Do not submit when persistence fails: a reload must not accidentally create another order.
      if (!replay && pending) { clearAttempt(sessionStorage); setPending(null); }
      attempt = replay ?? checkoutAttempt(sessionStorage, body, () => crypto.randomUUID()); setPending(attempt);
      const order = await browserRequest<CreatedOrder>('orders', locale, { method: 'POST', headers: { 'Idempotency-Key': attempt.key }, body: JSON.stringify(attempt.body) });
      try { rememberAttemptOrder(sessionStorage, order.public_token); } catch { /* The order page is still reachable from the email. */ }
      void refreshCart(locale).catch(() => {});
      if (onCreated) { onCreated(order); lock.current = false; setBusy(false); return; }
      if (order.payment_channel === 'wompi' && order.wompi) {
        setMessage(t.wompiRedirect);
        await openWompiWidget(order.wompi, result => {
          const id = result?.transaction?.id;
          if (id) void browserRequest(`orders/${encodeURIComponent(order.public_token)}/payment-sync`, locale, { method: 'POST', body: JSON.stringify({ transaction_id: id }) }).catch(() => {}).finally(() => router.replace(href('order', locale, order.public_token)));
          else router.replace(href('order', locale, order.public_token));
        });
        lock.current = false; setBusy(false); return;
      }
      clearAttempt(sessionStorage); setPending(null); navigating = true; router.replace(href('order', locale, order.public_token));
    } catch (error) {
      if (error instanceof ApiError) {
        const { code } = error.problem;
        if (error.status >= 400 && error.status < 500) { clearAttempt(sessionStorage); setPending(null); }
        if (code === 'idempotency_conflict') {
          sessionStorage.removeItem(attemptStorageKey);
          if (attempt) setPending(checkoutAttempt(sessionStorage, attempt.body, () => crypto.randomUUID()));
          fail(t.idempotencyConflict);
        }
        else if (['piece_reserved','piece_sold','piece_preorder'].includes(code)) { setConflict(true); fail(`${t.pieceConflict} ${(error.problem.skus ?? []).map(sku => `${cart.items.find(item => item.sku === sku)?.name ?? sku} (${sku})`).join(', ')}`); void refreshCart(locale).catch(() => {}); }
        else if (code === 'consent_required') {
          for (const name of ['terms', 'privacy']) { const input = form.current?.elements.namedItem(name); if (input instanceof HTMLInputElement) input.checked = false; }
          fail(t.consentRequired); setSettings({ ...settings, legal_versions: { terms: null, privacy: null } });
          void browserRequest<Settings>('site/settings', locale).then(setSettings).catch(() => fail(t.error));
        } else if (code.startsWith('coupon_')) { fail(t[couponMessageKey(code)]); setQuoteRetry(value => value + 1); }
        else if (code === 'cart_empty') { fail(t.empty); void refreshCart(locale).catch(() => {}); }
        else fail(t.error, fieldErrors(error.problem));
      } else fail(t.error);
    } finally { if (!navigating) { lock.current = false; setBusy(false); } }
  }
  function next() { if (!form.current) return; const fields = validateCheckoutFields(new FormData(form.current), [step], t); if (Object.keys(fields).length) { fail(t.reviewErrors, fields); return; } setMessage(''); setErrors({}); goStep(step === 'data' ? 'delivery' : 'summary'); }
  function field(name: string, label: string, autocomplete?: string, type = 'text', optional = false) {
    const id = name.replaceAll('.', '-'); return <label htmlFor={id}>{label}<input id={id} name={name} type={type} onChange={name === 'contact.email' ? event => setEmail(event.target.value) : undefined} autoComplete={autocomplete} inputMode={type === 'tel' ? 'tel' : type === 'email' ? 'email' : undefined} required={!optional} maxLength={name === 'shipping.notes' ? 1000 : 254} aria-invalid={!!errors[name]} aria-describedby={errors[name] ? `${id}-error` : undefined} /><span className="field-error" id={`${id}-error`}>{errors[name]?.join(' ')}</span></label>;
  }
  function consent(kind: 'terms' | 'privacy') { const link = settings.legal_pages.find(page => page.kind === kind); return <label className="checkbox-label"><input aria-label={t[kind]} id={kind} type="checkbox" name={kind} required aria-invalid={!!errors[kind]} aria-describedby={errors[kind] ? `${kind}-error` : undefined} />{link ? <Link href={link.href} target="_blank" className="text-link">{t[kind]} ↗</Link> : t[kind]}<span id={`${kind}-error`} className="field-error">{errors[kind]?.join(' ')}</span></label>; }
  if (!recovered || !loaded) return <p role="status">{t.loading}</p>;
  const created = pending?.order ? <div className="state-notice"><p>{t.orderInProgress}</p><p><Link className="text-link" href={href('order', locale, pending.order)}>{t.viewOrder} ↗</Link></p><button type="button" className="text-link" onClick={() => { try { clearAttempt(sessionStorage); } catch { /* Nothing to retire. */ } setPending(null); }}>{t.newPurchase}</button></div> : null;
  const blocking = !!pending && !pending.order;
  if (!blocking && !cart.items.length && !cartError) return <div className="empty-state">{created}<h2>{t.empty}</h2><Link className="text-link" href={href('catalog', locale)}>{t.explore} ↗</Link></div>;
  return <form className="checkout-form" ref={form} noValidate onSubmit={event => { event.preventDefault(); void submit(); }}>
    <p role="status" aria-live="polite">{busy ? (message === t.wompiRedirect ? t.wompiRedirect : t.submitting) : ''}</p>
    <div hidden={!message || message === t.wompiRedirect} ref={summary} tabIndex={-1} className={message ? 'error-summary' : ''} role={message ? 'alert' : undefined}>{message && <><p>{message}</p>{Object.entries(errors).map(([key, values]) => <a key={key} href={`#${key.replaceAll('.', '-')}`}>{values.join(' ')}</a>)}{conflict && <CustomPieceLink locale={locale} dict={dict} whatsapp={settings.whatsapp.general_url} />}</>}</div>
    {created}
    {blocking && pending && <div className="state-notice"><p>{t.resume}</p><p>{pending.body.contact.name} · {pending.body.contact.email}</p><button type="button" className="button" disabled={busy} onClick={() => { void submit(); }}>{busy ? t.submitting : t.retry}</button></div>}
    {cartError && <p role="alert">{t.error}<button type="button" className="text-link" onClick={() => { void refreshCart(locale).catch(() => {}); }}>{t.retry}</button></p>}
    <fieldset disabled={busy || blocking} className="checkout-details"><legend className="sr-only">{t.checkout}</legend><section hidden={stepped && step !== 'data'}><p className="eyebrow">01</p><h2 tabIndex={-1} ref={stepped && step === 'data' ? stepHeading : undefined}>{stepped ? t.yourData : t.contact}</h2>{field('contact.name',t.name,'name')}{field('contact.email',t.email,'email','email')}{field('contact.phone',t.phone,'tel','tel')}{stepped && <div className="step-actions"><button type="button" className="text-link" onClick={onBack}>← {t.back}</button><button type="button" className="button" onClick={next}>{t.next}</button></div>}</section>
    <section hidden={stepped && step !== 'delivery'}><p className="eyebrow">02 · Colombia</p><h2 tabIndex={-1} ref={stepped && step === 'delivery' ? stepHeading : undefined}>{t.delivery}</h2><label htmlFor="department">{t.department}<select aria-label={t.department} id="department" name="department" autoComplete="address-level1" value={department} onChange={event => { setDepartment(event.target.value); setMunicipalities([]); }}><option value="">{t.select}</option>{departments.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label htmlFor="shipping-municipality_code">{t.municipality}<select aria-label={t.municipality} id="shipping-municipality_code" name="shipping.municipality_code" autoComplete="address-level2" required disabled={!municipalities.length} aria-invalid={!!errors['shipping.municipality_code']} aria-describedby="municipality-error"><option value="">{t.select}</option>{municipalities.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}</select><span id="municipality-error" className="field-error">{errors['shipping.municipality_code']?.join(' ')}</span></label>{locationError && <p role="alert">{t.locationError} <button type="button" onClick={() => setLocationRetry(value => value + 1)}>{t.retry}</button></p>}{field('shipping.address_line',t.address,'address-line1')}{field('shipping.address_extra',t.extra,'address-line2','text',true)}{field('shipping.notes',t.notes,undefined,'text',true)}{stepped && <div className="step-actions"><button type="button" className="text-link" onClick={() => goStep('data')}>← {t.back}</button><button type="button" className="button" onClick={next}>{t.next}</button></div>}</section></fieldset>
    <fieldset hidden={stepped && step !== 'summary'} disabled={busy || blocking} className="checkout-summary"><legend className="sr-only">{t.summary}</legend><p className="eyebrow">03</p><h2 tabIndex={-1} ref={stepped && step === 'summary' ? stepHeading : undefined}>{t.summary}</h2>{cart.items.map(item => <div className="cart-line" key={item.sku}>{item.image && <Media image={item.image} sizes="80px" />}<div><h3>{item.name}</h3><p>{formatCOP(item.effective_price.amount_cents,locale)}</p>{!item.purchasable && <p className="state-notice">{t.reserved}</p>}</div></div>)}
    <details><summary>{t.coupon}</summary><label htmlFor="coupon">{t.couponCode}<input id="coupon" value={couponInput} maxLength={80} onChange={event => setCouponInput(event.target.value)} /></label><button type="button" className="text-link" onClick={() => { setCoupon(couponInput.trim()); setQuoteRetry(value => value + 1); }}>{t.apply}</button></details>
    <label className="checkbox-label"><input type="checkbox" checked={certificate} onChange={event => setCertificate(event.target.checked)} />{t.wantCertificate}{(settings.certificate_price_cents ?? 0) > 0 && ` · ${formatCOP(settings.certificate_price_cents!, locale)}`}</label>
    <div aria-live="polite" aria-busy={!quote && !quoteError}>{quote ? <>{quote.coupon && <p className={quote.coupon.applied ? '' : 'field-error'}>{quote.coupon.applied ? t.couponApplied : t[couponMessageKey(quote.coupon.reason ?? '')]}</p>}<Totals data={quote} locale={locale} dict={dict} /></> : <p>{quoteError ? t.error : t.loading}</p>}</div>{quoteError && <button type="button" className="text-link" onClick={() => setQuoteRetry(value => value + 1)}>{t.retry}</button>}<p>{t.freeShipping}</p>
    {(['wompi','manual'] as const).filter(value => quote?.payment_channels.includes(value)).map(value => <label className="payment-choice" key={value}><input type="radio" name="payment_channel" value={value} checked={channel === value} onChange={() => setChannel(value)} /><span>{value === 'wompi' ? t.online : t.manual}<small>{value === 'wompi' ? t.onlineHelp : t.manualHelp.replace('{hours}', String(settings.manual_reservation_hours ?? 24))}</small></span></label>)}{quote && !quote.payment_channels.length && <p role="alert">{t.paymentUnavailable}</p>}
    {consent('terms')}{consent('privacy')}{stepped && <button type="button" className="text-link" onClick={() => goStep('delivery')}>← {t.back}</button>}{!legalReady && <p className="field-error">{t.legalUnavailable}</p>}<button className="button" type="submit" disabled={busy || !quote || !legalReady || !quote.payment_channels.length || !cart.items.some(item => item.purchasable) || quote.coupon?.applied === false}>{busy ? t.submitting : `${t.confirm}${quote ? ` · ${formatCOP(quote.total_cents,locale)}` : ''}`}</button></fieldset>
  </form>;
}
