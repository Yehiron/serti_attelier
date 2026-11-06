import test from 'node:test';
import assert from 'node:assert/strict';
import { orderViewState } from './order-state.ts';
import { paymentAttemptKey, clearPaymentAttempt } from './commerce.ts';
import type { PaymentDetails, PaymentStatus } from './api/types.ts';
test('every backend status and flag combination selects safe order controls', () => {
  for (const status of ['pending','approved','declined','voided','error','expired','awaiting_manual_payment'] as PaymentStatus[]) {
    for (const can_retry of [false,true]) for (const unavailable of [false,true,undefined]) for (const present of [false,true]) for (const attempt of [null,'PENDING','APPROVED','DECLINED','ERROR','VOIDED'] as const) {
      const order: PaymentDetails = { wompi: present ? { checkout_url:'https://checkout.wompi.co/p/',fields:{} } : null, payment_unavailable:unavailable, payment:{status,can_retry,last_attempt:attempt ? {status:attempt,reference:'SRT-01',payment_method_type:null} : null} };
      const view = orderViewState(order); const onlineActive = ['pending','declined','error'].includes(status);
      assert.equal(view.status,status);
      assert.equal(view.unavailable, onlineActive && unavailable === true);
      assert.equal(view.retry, onlineActive && can_retry && unavailable !== true);
      assert.equal(view.pay,status === 'pending' && present && unavailable !== true && !view.retry);
      assert.equal(view.confirming,status === 'pending' && attempt === 'PENDING');
      assert.equal(view.active, ['pending','awaiting_manual_payment'].includes(status) || view.retry);
      assert.equal(view.failed,['declined','voided','error'].includes(status));
      assert.equal(view.heading, status === 'approved' ? 'approved' : status === 'expired' ? 'expired' : status === 'awaiting_manual_payment' ? 'manualHeading' : status === 'pending' ? 'completePayment' : 'orderFailed');
    }
  }
});
test('retry keys survive uncertain responses, isolate orders and rotate for a different failed attempt', () => {
  const memory = new Map<string,string>(); const storage = { getItem:(key:string) => memory.get(key) ?? null,setItem:(key:string,value:string) => { memory.set(key,value); },removeItem:(key:string) => { memory.delete(key); } };
  let count=0; const uuid=() => `key-${++count}`;
  assert.equal(paymentAttemptKey(storage,'token-a','SRT-01',uuid),'key-1');
  assert.equal(paymentAttemptKey(storage,'token-a','SRT-01',uuid),'key-1');
  assert.equal(paymentAttemptKey(storage,'token-b','SRT-01',uuid),'key-2');
  assert.equal(paymentAttemptKey(storage,'token-a','SRT-02',uuid),'key-3');
  clearPaymentAttempt(storage,'token-a'); assert.equal(paymentAttemptKey(storage,'token-a','SRT-02',uuid),'key-4');
  assert.equal(paymentAttemptKey(storage,'token-b','SRT-01',uuid),'key-2');
});

test('timeline highlights the operative state and leaves future steps muted', async () => {
  const { fulfillmentTimeline } = await import('./order-state.ts');
  const keys = ['received','paid','preparing','shipped','delivered'] as const;
  for (const status of ['unfulfilled','preparing','shipped','delivered','cancelled','returned'] as const) {
    const timeline = (status === 'cancelled' ? ['received','paid','cancelled'] as const : status === 'returned' ? [...keys,'returned'] as const : keys).map(key => ({ key, label_key:key, at:key === 'received' ? '2026-01-01T00:00:00Z' : null }));
    const steps = fulfillmentTimeline({status,carrier:'',tracking_number:'',shipped_at:null,delivered_at:null,timeline}, true);
    assert.equal(steps.filter(s => s.current).length, 1);
    assert.equal(steps.find(s => s.current)?.key, status === 'unfulfilled' ? 'paid' : status);
    const current = steps.findIndex(s => s.current);
    assert.ok(steps.slice(current + 1).every(s => s.future));
    if (status !== 'cancelled' && status !== 'returned') assert.ok(steps.slice(0,current).every(s => s.complete));
  }
});

test('tracking and unavailable messages exist in both storefront languages', async () => {
  const { readFileSync } = await import('node:fs');
  for (const lang of ['es','en']) {
    const dict = JSON.parse(readFileSync(new URL(`../app/[locale]/dictionaries/${lang}.json`, import.meta.url), 'utf8')).commerce;
    for (const key of ['received','paid','preparing','shipped','delivered','cancelled','returned','trackShipment','linkUnavailable','tooManyRequests','paymentReview','cancelledHelp']) assert.ok(dict[key]?.length > 5);
    if (lang === 'es') {
      assert.equal(dict.paymentReview, 'Estamos revisando tu pago; te contactaremos');
      assert.equal(dict.linkUnavailable, 'Este enlace ya no está disponible. Escríbenos y con gusto te ayudamos.');
    }
  }
});
