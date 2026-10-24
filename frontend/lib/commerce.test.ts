import test from 'node:test';
import assert from 'node:assert/strict';
import { checkoutAttempt, checkoutPayload, clearAttempt, couponMessageKey, emptyCart, fieldErrors, formatDeadline, mergeCart, normalizePhone, readAttempt, type CartItem } from './commerce.ts';
const item = (sku: string, purchasable = true): CartItem => ({ sku, slug: sku, name: sku, image: null, price: { amount_cents: 10000, currency: 'COP' }, sale_price: null, effective_price: { amount_cents: 10000, currency: 'COP' }, sale_state: purchasable ? 'available' : 'reserved', purchasable });
test('server reconciliation deduplicates unique pieces, keeps reserved and reconciles removed notices', () => {
  const first = mergeCart(emptyCart, { ...emptyCart, items: [item('A'),item('A'),item('B',false)], subtotal: { amount_cents: 10000, currency: 'COP' }, count: 3 });
  assert.equal(first.count,2); assert.equal(first.items[1].purchasable,false); assert.equal(first.subtotal.amount_cents,10000);
  const removed = mergeCart(first,{ ...emptyCart, removed: [{ sku:'A',name:'A',reason:'sold' }] });
  const next = mergeCart(removed,emptyCart); assert.equal(next.items.length,0); assert.equal(next.removed.length,1);
  assert.equal(mergeCart(next,{ ...emptyCart,items:[item('A')] }).removed.length,0);
});
function body() {
  const form = new FormData();
  for (const [key,value] of Object.entries({ 'contact.name':'  Ana Pérez  ','contact.email':' ANA@EXAMPLE.COM ','contact.phone':'(300) 123 4567','shipping.municipality_code':' 05001 ','shipping.address_line':' Calle 1 ','shipping.address_extra':' Apto 2 ','shipping.notes':' Timbre ','terms':'on','privacy':'on','total_cents':'1','skus':'FAKE' })) form.set(key,value);
  return checkoutPayload(form,{ coupon:'  HOLA  ', certificate:true, channel:'manual',terms:3,privacy:2,locale:'es' });
}
test('checkout payload trims contact/address, normalizes phone and never accepts client prices or SKUs', () => {
  assert.deepEqual(body(),{ contact:{name:'Ana Pérez',email:'ana@example.com',phone:'+573001234567'},shipping:{municipality_code:'05001',address_line:'Calle 1',address_extra:'Apto 2',notes:'Timbre'},coupon_code:'HOLA',wants_certificate:true,payment_channel:'manual',accepted_terms_version:3,accepted_privacy_version:2,locale:'es' });
  assert.equal(normalizePhone('+57 300-123-4567'),'+573001234567');
  const blank=checkoutPayload(new FormData(),{coupon:'',certificate:false,channel:'wompi',terms:3,privacy:2,locale:'en'});
  assert.equal(blank.accepted_terms_version,null); assert.equal(blank.accepted_privacy_version,null);
});
test('attempt persistence replays the exact body and key after edits or reload, until explicitly cleared', () => {
  const memory = new Map<string,string>(); const storage = { getItem:(key:string) => memory.get(key) ?? null, setItem:(key:string,value:string) => { memory.set(key,value); }, removeItem:(key:string) => { memory.delete(key); } };
  let count = 0; const uuid=() => `uuid-${++count}`; const payload=body();
  const first=checkoutAttempt(storage,payload,uuid); assert.equal(first.key,'uuid-1');
  assert.deepEqual(checkoutAttempt(storage,{...payload,coupon_code:'OTHER'},uuid),first);
  assert.deepEqual(readAttempt(storage),first); assert.equal(count,1);
  clearAttempt(storage); assert.equal(readAttempt(storage),null); assert.equal(checkoutAttempt(storage,payload,uuid).key,'uuid-2');
  memory.set('serti_checkout_attempt','broken'); assert.equal(readAttempt(storage),null);
});
test('nested and dotted API validation errors map to form names without losing messages', () => {
  assert.deepEqual(fieldErrors({ code:'validation_error',errors:{contact:{email:['Invalid'],phone:['Required']},'shipping.address_line':['Required'],non_field_errors:['Try again']} }),{'contact.email':['Invalid'],'contact.phone':['Required'],'shipping.address_line':['Required'],non_field_errors:['Try again']});
  assert.deepEqual(fieldErrors({code:'network_unavailable'}),{});
});
test('every stable coupon reason maps to a translation key', () => {
  for (const [reason,key] of Object.entries({coupon_invalid:'couponInvalid',coupon_expired:'couponExpired',coupon_exhausted:'couponExhausted',coupon_not_applicable:'couponNotApplicable',coupon_min_subtotal:'couponMinSubtotal'})) assert.equal(couponMessageKey(reason),key);
  assert.equal(couponMessageKey('unknown'),'couponInvalid');
});
test('deadlines are consistently rendered in Bogota even across UTC date boundaries', () => {
  const value='2026-10-25T02:30:00Z';
  assert.match(formatDeadline(value,'en'),/October 24, 2026/); assert.match(formatDeadline(value,'en'),/9:30\s?PM/);
  assert.match(formatDeadline(value,'es'),/24 de octubre de 2026/);
});
