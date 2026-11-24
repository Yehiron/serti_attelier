'use client';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { PaymentDetails } from '@/lib/api/types';
import type { Locale } from '@/lib/i18n';
import { browserRequest } from '@/lib/cart';
import { ApiError } from '@/lib/api/problem';
import { clearAttempt, clearAttemptForOrder, clearPaymentAttempt, paymentAttemptKey } from '@/lib/commerce';
import { orderViewState } from '@/lib/order-state';
import { openWompiWidget, withoutTransactionId } from '@/lib/wompi';

export function OrderPayment({ order, token, locale, t, paused = false }: { paused?: boolean; order: PaymentDetails; token: string; locale: Locale; t: Dictionary['commerce'] }) {
  const view = orderViewState(order); const router = useRouter();
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const locked = useRef(false); const synced = useRef<string | null>(null); const previous = useRef(view.status);
  useEffect(() => {
    // This order now has its own payment controls: the checkout must not keep replaying it.
    try { clearAttemptForOrder(sessionStorage, token); } catch { /* Storage unavailable. */ }
  }, [token]);
  useEffect(() => {
    if (view.status === 'approved') {
      try { clearAttempt(sessionStorage); clearPaymentAttempt(sessionStorage, token); } catch { /* Payment is already confirmed. */ }
    }
    if (previous.current !== view.status && (view.status === 'approved' || view.status === 'expired' || view.failed)) document.getElementById('order-heading')?.focus();
    previous.current = view.status;
  }, [view.status, view.failed, token]);
  useEffect(() => {
    // Read in an effect: no request-bound search params enter the prerendered tree.
    const transaction = new URL(window.location.href).searchParams.get('id');
    if (!transaction || synced.current === `${token}:${transaction}`) return;
    synced.current = `${token}:${transaction}`;
    void browserRequest(`orders/${encodeURIComponent(token)}/payment-sync`, locale, { method: 'POST', body: JSON.stringify({ transaction_id: transaction }) })
      .catch(error => {
        if (error instanceof ApiError && error.status === 429) setMessage(t.tooManyRequests);
        else if (!(error instanceof ApiError && error.status === 404)) setMessage(t.syncDelayed);
      }).finally(() => {
        router.refresh();
        const current = new URL(window.location.href);
        if (current.searchParams.get('id') === transaction) window.history.replaceState(window.history.state, '', withoutTransactionId(current.href));
      });
  }, [token, locale, router, t.syncDelayed, t.tooManyRequests]);
  async function pay(retry: boolean) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setMessage(t.wompiRedirect);
    try {
      const checkout = retry ? (await browserRequest<Pick<PaymentDetails, 'wompi'>>(`orders/${encodeURIComponent(token)}/payment-attempts`, locale, {
        method: 'POST', headers: { 'Idempotency-Key': paymentAttemptKey(sessionStorage, token, order.payment.last_attempt?.reference ?? '', () => crypto.randomUUID()) },
      })).wompi : order.wompi;
      if (!checkout) { router.refresh(); setMessage(t.onlineUnavailable); }
      else { await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))); await openWompiWidget(checkout, result => { const id = result?.transaction?.id; if (id) void browserRequest(`orders/${encodeURIComponent(token)}/payment-sync`, locale, { method: 'POST', body: JSON.stringify({ transaction_id: id }) }).catch(() => setMessage(t.syncDelayed)).finally(() => router.refresh()); else router.refresh(); }); setMessage(''); }
    } catch (error) {
      if (error instanceof ApiError && error.problem.code === 'payment_not_retryable') { router.refresh(); setMessage(''); }
      else setMessage(error instanceof ApiError && error.status === 429 ? t.tooManyRequests : t.error);
    }
    locked.current = false; setBusy(false);
  }
  if (paused) return message ? <p role="status">{message}</p> : null;
  return <div className="order-payment" aria-live="polite" aria-busy={busy}>
    {view.confirming && <p>{t.confirmingPayment}</p>}
    {view.unavailable && <p className="payment-notice">{t.onlineUnavailable}</p>}
    {view.retry && <><p>{t.paymentRetryHelp}</p><button type="button" className="button" disabled={busy} onClick={() => void pay(true)}>{busy ? t.wompiRedirect : t.retry}</button></>}
    {view.pay && <><button type="button" className={view.confirming ? 'button payment-secondary' : 'button'} disabled={busy} onClick={() => void pay(false)}>{busy ? t.wompiRedirect : t.payWompi}</button><p>{t.securePayment}</p></>}
    {message && <p role="status">{message}</p>}
  </div>;
}
