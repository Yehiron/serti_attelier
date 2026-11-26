import { test } from 'node:test';
import assert from 'node:assert/strict';
import { collectionLink, pieceEyebrow, stoneColor } from './piece-look.ts';

test('eyebrow omits an empty piece number', () => {
  assert.equal(pieceEyebrow('Pieza única', ''), 'Pieza única');
  assert.equal(pieceEyebrow('Pieza única', ' 1 de 1 '), 'Pieza única · 1 de 1');
});
test('stone colors recognize Spanish and English names', () => {
  assert.equal(stoneColor('Esmeralda'), '#1f7a55');
  assert.equal(stoneColor('Rubí'), '#a51d38');
  assert.equal(stoneColor('Sapphire'), '#315d9b');
  assert.equal(stoneColor('Diamante'), '#eef1f3');
  assert.equal(stoneColor('Ópalo'), '#c9a96e');
  assert.equal(stoneColor('Esmeralda', '#123456'), '#123456');
  assert.equal(stoneColor('Esmeralda', ''), '#1f7a55');
});
test('collection link falls back to category and catalog', () => {
  const category = { name: 'Anillos', slug: 'anillos' };
  assert.equal(collectionLink('es', [{ name: 'Uno', slug: 'uno' }], category), '/es/colecciones/uno');
  assert.equal(collectionLink('es', [], category), '/es/joyeria/anillos');
  assert.equal(collectionLink('en', [], null), '/en/jewelry');
});
