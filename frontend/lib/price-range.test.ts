import test from 'node:test';
import assert from 'node:assert/strict';
import { centsToPesos, priceBounds, snapPrice } from './price-range.ts';

test('slider bounds widen the catalogue range to whole $50.000 steps', () => {
  assert.deepEqual(priceBounds(40_000_000, 600_000_000), { min: 400_000, max: 6_000_000 });
  assert.deepEqual(priceBounds(41_234_500, 598_000_000), { min: 400_000, max: 6_000_000 });
  assert.equal(priceBounds(null, 600_000_000), null);
  // A single price (or no results) leaves nothing to slide.
  assert.equal(priceBounds(500_000_000, 500_000_000), null);
});

test('values snap to the step grid inside the bounds', () => {
  const bounds = { min: 400_000, max: 6_000_000 };
  assert.equal(snapPrice(1_523_000, bounds), 1_500_000);
  assert.equal(snapPrice(1_526_000, bounds), 1_550_000);
  assert.equal(snapPrice(100_000, bounds), 400_000);
  assert.equal(snapPrice(9_000_000, bounds), 6_000_000);
});

test('query cents come back to the form as pesos', () => {
  assert.equal(centsToPesos('150000000'), 1_500_000);
  assert.equal(centsToPesos(null), null);
  assert.equal(centsToPesos(''), null);
});
