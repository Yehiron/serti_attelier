import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { contactPrefill, contactWhatsApp, validateContact, type ContactInput } from './contact.ts';
const valid: ContactInput = { name: 'Ana', email: 'ana@example.com', phone: '', topic: 'piece', piece_sku: 'ABC', message: 'Me interesa conocer esta pieza.', preferred_channel: 'email', accepted_privacy_version: 2, locale: 'es', website: '', elapsed_ms: 3000 };
test('prellena pieza o personalización', () => { assert.deepEqual(contactPrefill('?pieza=ABC'), { sku: 'ABC', topic: 'piece' }); assert.equal(contactPrefill('?tema=personalizacion').topic, 'custom'); });
test('valida los campos y consentimiento', () => { assert.deepEqual(validateContact(valid), []); assert.deepEqual(validateContact({ ...valid, email: 'mal', message: 'breve', accepted_privacy_version: null }), ['email', 'message', 'accepted_privacy_version']); });
test('construye el texto para WhatsApp', () => { assert.equal(contactWhatsApp(valid, 'una pieza', 'es'), 'Hola, soy Ana. Quiero hablar sobre una pieza sobre la pieza ABC: Me interesa conocer esta pieza.'); });

test('valida teléfonos', () => { assert.deepEqual(validateContact({ ...valid, phone: '(300) 111-2233' }), []); assert.deepEqual(validateContact({ ...valid, phone: '123' }), ['phone']); });
