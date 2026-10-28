import test from 'node:test';
import assert from 'node:assert/strict';
import { alternatePath } from './alternates.ts';

test('language alternates are site-relative so the switch never leaves the current host', () => {
  assert.equal(alternatePath('https://serti.localhost/en/pieces/ring?x=1'), '/en/pieces/ring?x=1');
  assert.equal(alternatePath('/es/piezas/anillo'), '/es/piezas/anillo');
});
