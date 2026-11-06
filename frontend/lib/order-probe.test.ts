import assert from 'node:assert/strict';
import test from 'node:test';
import { encodeOrderProbe, decodeOrderProbe } from './order-probe.ts';

test('request transport preserves successful and error responses, scoped to token and locale', () => {
  for (const status of [200, 429, 503]) {
    const probe = { token: 'test-token', locale: 'es', status, body: { number: 'SRT-1', name: 'Pieza única' } };
    const encoded = encodeOrderProbe(probe);
    assert.deepEqual(decodeOrderProbe(encoded, 'test-token', 'es'), probe);
    assert.equal(decodeOrderProbe(encoded, 'other', 'es'), null);
    assert.equal(decodeOrderProbe(encoded, 'test-token', 'en'), null);
  }
  assert.equal(decodeOrderProbe(null, 'a', 'es'), null);
  assert.equal(decodeOrderProbe('invalid', 'a', 'es'), null);
});
