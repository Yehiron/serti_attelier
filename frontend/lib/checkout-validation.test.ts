import test from 'node:test';
import assert from 'node:assert/strict';
import { validateCheckoutFields } from './checkout-validation.ts';
const messages = { required: 'required', emailInvalid: 'email', phoneInvalid: 'phone' };
test('valida únicamente los campos del paso y acepta datos válidos', () => {
  const data = new FormData();
  assert.deepEqual(validateCheckoutFields(data, ['data'], messages), { 'contact.name': ['required'], 'contact.email': ['email'], 'contact.phone': ['phone'] });
  data.set('contact.name', 'Ana'); data.set('contact.email', 'ana@example.com'); data.set('contact.phone', '300 123 4567');
  assert.deepEqual(validateCheckoutFields(data, ['data'], messages), {});
  assert.deepEqual(validateCheckoutFields(data, ['delivery'], messages), { 'shipping.municipality_code': ['required'], 'shipping.address_line': ['required'] });
  data.set('shipping.municipality_code', '05001'); data.set('shipping.address_line', 'Calle 1');
  assert.deepEqual(validateCheckoutFields(data, ['delivery'], messages), {});
  assert.deepEqual(validateCheckoutFields(data, ['summary'], messages), { terms: ['required'], privacy: ['required'] });
});
