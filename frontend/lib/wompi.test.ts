import test from 'node:test';
import assert from 'node:assert/strict';
import { wompiFormModel, withoutTransactionId, submitWompiCheckout } from './wompi.ts';
import type { WompiCheckout } from './api/types.ts';
const checkout = (): WompiCheckout => ({ checkout_url: 'https://checkout.wompi.co/p/', fields: {
  'public-key': 'pub_test_example', currency: 'COP', 'amount-in-cents': '400000000', reference: 'SRT-000123-01', 'signature:integrity': 'abc123', 'expiration-time': '2026-10-26T20:28:50.000Z', 'redirect-url': 'https://serti.example/es/pedido/token', 'customer-data:full-name': 'Ana <&"', 'shipping-address:country': 'CO',
} });
test('checkout maps fields literally to a GET form and coerces primitive values to strings', () => {
  const input = checkout(); Object.assign(input.fields, { 'amount-in-cents': 400000000 });
  const model = wompiFormModel(input);
  assert.equal(model.method, 'GET'); assert.equal(model.action, 'https://checkout.wompi.co/p/');
  assert.deepEqual(Object.fromEntries(model.fields.map(field => [field.name, field.value])), checkout().fields);
  assert.equal(input.fields['amount-in-cents'], 400000000);
});
test('only the exact Wompi action is allowed', () => {
  for (const checkout_url of ['http://checkout.wompi.co/p/', 'https://checkout.wompi.co/p', 'https://checkout.wompi.co/p/?x=1', 'https://checkout.wompi.co.evil/p/', 'javascript:alert(1)', 'https://checkout.wompi.co@evil.example/p/']) assert.throws(() => wompiFormModel({ ...checkout(), checkout_url }));
});
test('rejects unexpected fields, unsafe redirect URLs, missing fields and nonprimitive values', () => {
  for (const fields of [{ unexpected: 'javascript:alert(1)' }, { action: 'https://evil.example' }, { 'redirect-url': 'javascript:alert(1)' }, { 'redirect-url': 'data:text/html,hello' }, { reference: '' }, { currency: null }, { reference: {} }]) assert.throws(() => wompiFormModel({ ...checkout(), fields: { ...checkout().fields, ...fields } } as unknown as WompiCheckout));
});
test('removes all transaction ids while preserving unrelated params and hash', () => {
  assert.equal(withoutTransactionId('https://serti.example/es/pedido/t?id=123&locale=es&id=456#summary'), '/es/pedido/t?locale=es#summary');
  assert.equal(withoutTransactionId('https://serti.example/en/pedido/t?id=123'), '/en/pedido/t');
  assert.equal(withoutTransactionId('https://serti.example/en/pedido/t?foo=bar'), '/en/pedido/t?foo=bar');
});
test('submits a native GET form with hidden literal inputs in the same tab until navigation', () => {
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  const previousForm = Object.getOwnPropertyDescriptor(globalThis, 'HTMLFormElement');
  const children: { type: string; name: string; value: string }[] = []; let submitted = false; let removed = false;
  const form = { method: '', action: '', hidden: false, appendChild: (input: typeof children[number]) => children.push(input), remove: () => { removed = true; } };
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { createElement: (tag: string) => tag === 'form' ? form : {}, body: { appendChild: (node: unknown) => assert.equal(node, form) } } });
  Object.defineProperty(globalThis, 'HTMLFormElement', { configurable: true, value: { prototype: { submit() { submitted = true; assert.equal(this, form); } } } });
  try { submitWompiCheckout(checkout()); assert.equal(submitted, true); assert.equal(removed, false); assert.equal(form.method, 'GET'); assert.equal(form.action, checkout().checkout_url); assert.equal('target' in form, false); assert.ok(children.every(input => input.type === 'hidden')); assert.deepEqual(Object.fromEntries(children.map(input => [input.name,input.value])), checkout().fields); }
  finally {
    if (previousDocument) Object.defineProperty(globalThis, 'document', previousDocument); else Reflect.deleteProperty(globalThis, 'document');
    if (previousForm) Object.defineProperty(globalThis, 'HTMLFormElement', previousForm); else Reflect.deleteProperty(globalThis, 'HTMLFormElement');
  }
});

test('widget maps validated fields and integer amount', async () => {
  const { widgetConfig } = await import('./wompi.ts');
  const input = checkout(); Object.assign(input.fields, { 'customer-data:email': 'ana@example.com', 'customer-data:phone-number': '3001234567', 'shipping-address:phone-number': '3001234567', 'shipping-address:city': 'Medellín' });
  const config = widgetConfig(input);
  assert.equal(config.amountInCents, 400000000); assert.equal(config.signature.integrity, 'abc123');
  assert.deepEqual(config.customerData, { email: 'ana@example.com', fullName: 'Ana <&"', phoneNumber: '3001234567' });
  assert.deepEqual(config.shippingAddress, { country: 'CO', city: 'Medellín', phoneNumber: '3001234567' });
  for (const amount of ['1.5', '-1', '1e3', '9007199254740992']) assert.throws(() => widgetConfig({ ...input, fields: { ...input.fields, 'amount-in-cents': amount } }));
  assert.throws(() => widgetConfig({ ...input, checkout_url: 'https://evil.example/' }));
  assert.throws(() => widgetConfig({ ...input, fields: { ...input.fields, extra: 'x' } }));
});

test('widget falls back to the form when script fails', async () => {
  const { openWompiWidget } = await import('./wompi.ts');
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, 'document'); const oldWindow = Object.getOwnPropertyDescriptor(globalThis, 'window'); const oldForm = Object.getOwnPropertyDescriptor(globalThis, 'HTMLFormElement');
  let submitted = false;
  const form = { appendChild() {}, remove() {} };
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { setTimeout, clearTimeout } });
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { createElement: (tag: string) => tag === 'form' ? form : { remove() {} }, head: { appendChild: (script: { onerror: () => void }) => script.onerror() }, body: { appendChild() {} } } });
  Object.defineProperty(globalThis, 'HTMLFormElement', { configurable: true, value: { prototype: { submit() { submitted = true; } } } });
  try { await openWompiWidget(checkout(), () => {}); assert.equal(submitted, true); }
  finally { for (const [key, descriptor] of [['document', oldDocument], ['window', oldWindow], ['HTMLFormElement', oldForm]] as const) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else Reflect.deleteProperty(globalThis, key); } }
});
