import test from 'node:test';
import assert from 'node:assert/strict';
import { cartSnapshot, closeCart, openCart } from './cart.ts';

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
