import test from 'node:test';
import assert from 'node:assert/strict';
import { cartSnapshot, closeCart, openCart, refreshCart } from './cart.ts';

test('opening identifies the added piece only for that opening', () => {
  openCart({ added: 'SKU-1' });
  assert.equal(cartSnapshot().added, 'SKU-1');
  assert.equal(cartSnapshot().drawer, true);
  closeCart();
  assert.equal(cartSnapshot().added, null);
  openCart();
  assert.equal(cartSnapshot().added, null);
  closeCart();
});

test('a successful cart reload clears a previous request error', async () => {
  const originalFetch = globalThis.fetch;
  const previousWindow = globalThis.window;
  Object.assign(globalThis, { window: { location: { origin: 'https://example.test' } } });
  let fails = true;
  Object.assign(globalThis, { fetch: async () => fails
    ? new Response('', { status: 502 })
    : Response.json({ items: [], removed: [], count: 0, subtotal: { amount_cents: 0, currency: 'COP' } }) });
  try {
    await assert.rejects(refreshCart('es'));
    assert.equal(cartSnapshot().error, true);
    fails = false;
    await refreshCart('es');
    assert.equal(cartSnapshot().error, false);
  } finally {
    globalThis.fetch = originalFetch;
    Object.assign(globalThis, { window: previousWindow });
  }
});
