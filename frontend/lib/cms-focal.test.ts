import assert from 'node:assert/strict';
import test from 'node:test';
import { focalPosition } from './cms-focal.ts';

test('el punto de interés define object-position sin cambiar el valor histórico por defecto', () => {
  assert.equal(focalPosition({}), undefined);
  assert.equal(focalPosition({ focal: { x: .25, y: .8 } }), '25% 80%');
  assert.equal(focalPosition({ focal: { x: -1, y: 2 } }), '0% 100%');
  assert.equal(focalPosition({ focal: { x: NaN, y: 0 } }), undefined);
});


test('Imagen con texto conserva el punto de interés de cada dispositivo', async () => {
  const { createElement } = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');
  const { RegistrySection } = await import('../components/registry-section.ts');
  const image = { src: '/foto.webp', srcset: '', width: 800, height: 1000, alt: 'Taller', focal: { x: .7, y: .3 } };
  const html = renderToStaticMarkup(createElement(RegistrySection, { section: {
    id: 1, schema_version: 1, kind: 'image_text', title: 'Taller', body: 'Texto', eyebrow: '',
    image, mobile_image: { ...image, focal: { x: .2, y: .4 } }, image_position: 'left', cta: null,
  } }));
  assert.match(html, /--cms-focal:70% 30%/);
  assert.match(html, /--cms-mobile-focal:20% 40%/);
  assert.match(html, /class="cms-focal-responsive"/);
});
