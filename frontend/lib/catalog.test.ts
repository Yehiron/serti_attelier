import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogQuery } from './catalog.ts';
test('GET filter normalization combines stones and preserves route scope', () => {
 const query = catalogQuery({stone:['emerald','diamond'],category:'rings',page:'2',token:'secret'}, {category:'earrings'});
 assert.equal(query.get('stone'),'emerald,diamond');assert.equal(query.get('category'),'earrings');assert.equal(query.get('availability'),'available');assert.equal(query.has('token'),false);
});

test('price filters are typed in pesos and sent to the API in cents', () => {
  assert.equal(catalogQuery({ price_min: '1500000', price_max: ' 4000000 ' }).toString(), 'price_min=150000000&price_max=400000000&availability=available');
  for (const bad of ['-1', '1.5', 'abc', '1e9', '9999999999999']) assert.equal(catalogQuery({ price_min: bad }).has('price_min'), false);
});
