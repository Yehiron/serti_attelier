import { test } from 'node:test';
import assert from 'node:assert/strict';
import { breadcrumbs, itemList, jsonLd, largestImage, pieceTitle, pieceDescription, listingCopy, productSchema } from './seo.ts';
import type { PieceDetail } from './api/types.ts';
const piece = { name: 'Anillo', sku: 'A', short_description: 'Oro', attributes: { metal: 'oro', metal_purity: '18k' }, stones: [{ name: 'esmeralda', slug: 'esmeralda' }], materials: [{ name: 'oro', slug: 'oro' }], gallery: [{ src: '/960', srcset: '/960 960w, /1600 1600w', width: 1600, height: 1600, alt: 'Anillo' }], price: { amount_cents: 10000, currency: 'COP' }, sale_price: null, sale_state: 'preorder' } as PieceDetail;
test('título y esquema usan datos de la pieza y máxima resolución', () => {
  assert.match(pieceTitle(piece, 'es'), /Anillo · oro 18k con esmeralda/);
  assert.equal(largestImage(piece.gallery[0]), '/1600');
  const product = productSchema(piece, '/es/piezas/anillo', 'https://example.com', '/es/legal/devoluciones');
  assert.equal(product.offers.availability, 'https://schema.org/PreOrder');
  assert.equal(product.image[0], 'https://example.com/1600');
  assert.equal(product.offers.shippingDetails.shippingRate.value, 0);
});
test('listas limitadas, enlaces absolutos y JSON seguro', () => {
  const items = Array.from({ length: 25 }, (_, i) => ({ name: String(i), url: '/p' }));
  assert.equal(itemList(items, 'https://example.com').itemListElement.length, 20);
  assert.equal(breadcrumbs(items.slice(0, 1), 'https://example.com').itemListElement[0].item, 'https://example.com/p');
  assert.ok(!jsonLd({ x: '</script>' }).includes('<'));
});

test('plantillas SEO distinguen listados y evitan duplicaciones', () => {
  for (const language of ['es', 'en'] as const) {
    for (const kind of ['catalog', 'category', 'stone', 'collection'] as const) assert.ok(listingCopy(kind, kind === 'stone' ? 'Esmeralda' : 'Anillos', language).description.length <= 160);
    assert.ok(pieceTitle({ ...piece, name: 'Anillo de Oro con Esmeralda' }, language).length <= 65);
    assert.ok(pieceDescription({ ...piece, short_description: '' }, language).length <= 160);
  }
  assert.match(listingCopy('category', 'Pulsera', 'es').description, /^Joyas de pulsera hechas/);
  assert.match(listingCopy('stone', 'Esmeralda', 'es').title, /^Joyas con esmeralda colombiana/);
  assert.match(listingCopy('collection', 'Regalos', 'es').description, /^Regalos:/);
  assert.equal((pieceDescription({ ...piece, short_description: 'Una pieza única.' }, 'es').match(/pieza única/gi) || []).length, 1);
});
