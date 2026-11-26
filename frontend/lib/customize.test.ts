import { test } from 'node:test';
import assert from 'node:assert/strict';
import { categoryKind, customizeMessage, customizeColor } from './customize.ts';

test('category singular and icon mapping, including fallback', () => {
  assert.deepEqual(categoryKind('anillos', 'Anillos'), { singular: 'anillo', icon: 'ring' });
  assert.deepEqual(categoryKind('earrings', 'Earrings'), { singular: 'earrings', icon: 'earrings' });
  assert.deepEqual(categoryKind('otro', 'Otra'), { singular: 'Otra', icon: 'generic' });
});
test('messages include selections and trimmed notes in both languages', () => {
  assert.equal(customizeMessage('es', 'Anillo', 'Rubí', 'Oro', '  Hola  '), 'Hola SERTI, vengo de la página de personalización. Quiero una joya: anillo con rubí en oro. Hola');
  assert.equal(customizeMessage('en', 'Ring', 'Ruby', 'Gold', ''), 'Hello SERTI, I’m coming from the customization page. I would like a piece of jewelry: ring with ruby in gold.');
  assert.match(customizeMessage('es', 'Aretes', null, null, ''), /asesoren con la piedra y el metal\.$/);
  assert.match(customizeMessage('en', 'Ring', null, 'Gold', ''), /advice on the stone\.$/);
  assert.equal(customizeMessage('es', 'Anillo', 'Rubí', 'Oro', 'x'.repeat(310)).split('. ').pop()?.length, 300);
});

test('customizeColor usa el tono guardado y conserva la deducción', () => {
  assert.equal(customizeColor('Oro blanco', true, '#123456'), '#123456');
  assert.equal(customizeColor('Oro blanco', true, ''), '#dcdcd8');
  assert.equal(customizeColor('Oro rosa', true), '#e3a98e');
});
