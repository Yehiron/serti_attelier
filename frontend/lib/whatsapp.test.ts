import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('el glifo de WhatsApp conserva un viewBox cuadrado y queda oculto a lectores de pantalla', () => {
  const source = readFileSync(new URL('../components/whatsapp.tsx', import.meta.url), 'utf8');
  const svg = source.match(/<svg\b([^>]*)>/)?.[1];
  assert.ok(svg);
  const viewBox = svg.match(/viewBox="([^"]+)"/)?.[1].split(/\s+/).map(Number);
  assert.deepEqual(viewBox, [0, 0, 32, 32]);
  assert.match(svg, /aria-hidden="true"/);
  assert.match(source, /aria-label=\{dict\.ui\.whatsapp\}/);
});
