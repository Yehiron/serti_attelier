import test from 'node:test';
import assert from 'node:assert/strict';
import { href, routes, routeDecision, safePreviewPath } from './routes.ts';
test('localized contract and proxy canonical decisions', () => {
  for (const key of Object.keys(routes) as (keyof typeof routes)[]) {
    const [es,en] = routes[key];
    assert.equal(href(key,'en','emerald'), `/en${en ? '/'+en : ''}/emerald`);
    if (es && es !== en) {
      assert.deepEqual(routeDecision(`/en/${es}/x`),{kind:'redirect',pathname:`/en/${en}/x`});
      assert.deepEqual(routeDecision(`/es/${en}/x`),{kind:'redirect',pathname:`/es/${es}/x`});
      assert.deepEqual(routeDecision(`/en/${en}/x`),{kind:'rewrite',pathname:`/en/${es}/x`});
    }
  }
  assert.equal(href('piece','es','una joya'),'/es/piezas/una%20joya');
  assert.deepEqual(routeDecision('/en'),{kind:'next',pathname:'/en'});
});
test('preview paths cannot escape locale or origin', () => {
  for (const value of ['//evil.test','/english','/es\\evil','https://evil.test','/es/../../preview','/en/../preview']) assert.equal(safePreviewPath(value),'/es');
  assert.equal(safePreviewPath('/en/pieces/ring?q=a'),'/en/pieces/ring?q=a');
});
test('cart, checkout and token order routes use their localized public URLs', () => {
  assert.equal(href('cart','es'),'/es/carrito'); assert.equal(href('cart','en'),'/en/cart');
  assert.equal(href('checkout','es'),'/es/checkout'); assert.equal(href('checkout','en'),'/en/checkout');
  assert.equal(href('order','es','public-token'),'/es/pedido/public-token'); assert.equal(href('order','en','public-token'),'/en/order/public-token');
  assert.deepEqual(routeDecision('/en/order/public-token'),{kind:'rewrite',pathname:'/en/pedido/public-token'});
  assert.deepEqual(routeDecision('/en/cart'),{kind:'rewrite',pathname:'/en/carrito'});
  assert.deepEqual(routeDecision('/en/checkout'),{kind:'next',pathname:'/en/checkout'});
  assert.deepEqual(routeDecision('/es/order/public-token'),{kind:'redirect',pathname:'/es/pedido/public-token'});
  assert.deepEqual(routeDecision('/en/pedido/public-token'),{kind:'redirect',pathname:'/en/order/public-token'});
  assert.deepEqual(routeDecision('/es/cart'),{kind:'redirect',pathname:'/es/carrito'});
  assert.deepEqual(routeDecision('/en/carrito'),{kind:'redirect',pathname:'/en/cart'});
});
