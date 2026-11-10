import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { RegistrySection } from '../components/registry-section.ts';
import { supportedSections } from './section-compat.ts';
import type { Section } from './api/sections.generated.ts';

for (const locale of ['es', 'en']) {
  test(`los nuevos bloques renderizan contenido publicado ${locale}`, () => {
    const title = locale === 'es' ? 'Tu historia en una joya' : 'Your story in a jewel';
    const image = { src: '/desktop.webp', srcset: '', width: 1600, height: 2000, alt: title };
    const photo = renderToStaticMarkup(h(RegistrySection, { section: {
      id: 1, kind: 'image_text', schema_version: 1, title, body: 'Primer párrafo\n\nSegundo párrafo',
      eyebrow: 'Atelier', image, mobile_image: { ...image, src: '/mobile.webp' }, image_position: 'right',
      cta: { label: locale === 'es' ? 'Personalizar' : 'Customize', href: `/${locale}/customize`, external: false },
    } }));
    for (const text of [title, '/mobile.webp', '(max-width: 760px)', 'image-right', 'Segundo párrafo']) assert.ok(photo.includes(text));
    assert.ok(photo.includes(`alt="${title}"`));
    const faq = renderToStaticMarkup(h(RegistrySection, { section: { id: 2, kind: 'faq', schema_version: 1, title,
      items: [{ question: '¿Cómo?', answer_html: '<p><strong>A tu medida</strong></p>' }] } }));
    assert.ok(faq.includes('<details>') && faq.includes('<summary>¿Cómo?</summary>') && faq.includes('<strong>A tu medida</strong>'));
    const process = renderToStaticMarkup(h(RegistrySection, { section: { id: 3, kind: 'process', schema_version: 1, title,
      steps: [{ title: 'Idea', description: 'Conversamos' }, { title: 'Taller', description: '' }] } }));
    assert.ok(process.includes('<ol>') && process.includes('Conversamos') && process.includes('Taller'));
  });
}
test('un tipo o versión futuros se omiten con aviso de servidor', () => {
  const warnings: unknown[][] = [];
  const warn = console.warn;
  console.warn = (...args: unknown[]) => warnings.push(args);
  try {
    const rows = supportedSections([{ id: 1, kind: 'future' }, { id: 2, kind: 'hero', schema_version: 9 },
      { id: 3, kind: 'statement', title: 'Marca', body: '' }] as unknown as Section[]);
    assert.deepEqual(rows.map(s => s.id), [3]);
    assert.equal(warnings.length, 2);
  } finally { console.warn = warn; }
});
