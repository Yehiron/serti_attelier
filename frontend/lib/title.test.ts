import test from 'node:test';
import assert from 'node:assert/strict';
import { titleLines } from './title.ts';

test('splits editorial titles on " / " and newlines', () => {
  assert.deepEqual(titleLines('Un poco de tierra. / Un poco de eternidad.'), ['Un poco de tierra.', 'Un poco de eternidad.']);
  assert.deepEqual(titleLines('Uno\nDos'), ['Uno', 'Dos']);
  assert.deepEqual(titleLines('Oro 18k/plata'), ['Oro 18k/plata']);
  assert.deepEqual(titleLines('  Solo  '), ['Solo']);
});
