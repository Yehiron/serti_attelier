import assert from 'node:assert/strict';
import test from 'node:test';
import { trackingHttpStatus, trackingPath, unavailableTrackingHtml } from './order-http.ts';
test('tracking preflight maps missing and expired to a real 404 only', () => {
  assert.equal(trackingHttpStatus(404), 404);
  assert.equal(trackingHttpStatus(410), 404);
  for (const status of [200, 429, 500, 503]) assert.equal(trackingHttpStatus(status), null);
});
test('preflight covers localized tracking routes and aliases only', () => {
  for (const language of ['es', 'en']) for (const route of ['pedido', 'order']) {
    assert.deepEqual(trackingPath(`/${language}/${route}/a-token`), { locale: language, token: 'a-token' });
  }
  for (const path of ['/es/catalogo/a-token', '/pedido/a-token', '/es/pedido/a-token/payment-sync', '/es/pedido/']) assert.equal(trackingPath(path), null);
});

test('missing link response is a complete localized document without a token', () => {
  for (const language of ['es', 'en'] as const) {
    const html = unavailableTrackingHtml(language);
    assert.ok(html.startsWith('<!doctype html>'));
    assert.ok(html.includes(`lang="${language}"`));
    assert.ok(html.includes('noindex,nofollow'));
    assert.ok(html.includes(`href="/${language}"`));
    assert.ok(!html.includes('public_token'));
  }
});

test('unavailable page uses store brand, local font and navigable header/footer', () => {
  const html = unavailableTrackingHtml('es');
  for (const fragment of ['<header class="site-header"', '<footer class="site-footer"', '/fonts/ninna-regular.otf', '/brand/logo/wordmark-wine.webp', 'Escríbenos y con gusto te ayudamos.', '/es/contacto']) assert.ok(html.includes(fragment));
});
