import test from 'node:test';
import assert from 'node:assert/strict';
import { formatCOP, whatsappUrl } from './format.ts';
test('COP uses cents and no decimal places in both locales', () => {
  assert.equal(formatCOP(123456700,'es'), '$ 1.234.567');
  assert.equal(formatCOP(123456700,'en'), 'COP 1,234,567');
  assert.equal(formatCOP(0,'en'),'COP 0');
});
test('WhatsApp encodes context and hides missing numbers', () => {
 assert.equal(whatsappUrl(null,'hola'),null);
 assert.equal(whatsappUrl('+57 300','hola & joya'),'https://wa.me/57300?text=hola%20%26%20joya');
});
