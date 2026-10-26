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
