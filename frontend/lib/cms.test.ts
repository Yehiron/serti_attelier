import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { PersonalizeContent } from '../components/personalize-content.ts';
import { protectDraftResponse, needsHomeFallback } from './cms-preview.ts';
import type { CmsPage } from './api/types.ts';

const copy = { process: 'De una idea a tu joya', faq: 'Preguntas frecuentes', steps: ['Cuéntanos'], questions: ['¿Cómo?'], answers: ['Escríbenos'] };
test('Personaliza renders published API steps and sanitized FAQ markup', () => {
  const page = { process: { title: 'Tus pasos', steps: [{ title: 'Diseñamos', description: 'A tu medida' }] }, faq: { title: 'Tus preguntas', items: [{ question: '¿Devoluciones?', answer_html: '<p>Consulta <a href="/es/legal/devoluciones">Devoluciones</a></p>' }] } } as CmsPage;
  const html = renderToStaticMarkup(createElement(PersonalizeContent, { page, copy }));
  for (const text of ['Tus pasos', 'Diseñamos', 'A tu medida', 'Tus preguntas', '/es/legal/devoluciones']) assert.ok(html.includes(text));
  assert.ok(!html.includes('Cuéntanos'));
});
test('old snapshots fall back to dictionaries and explicit empty publications stay empty', () => {
  const html = renderToStaticMarkup(createElement(PersonalizeContent, { copy }));
  for (const text of ['De una idea a tu joya', 'Cuéntanos', '¿Cómo?', 'Escríbenos']) assert.ok(html.includes(text));
  const empty = renderToStaticMarkup(createElement(PersonalizeContent, { page: { process: { title: '', steps: [] }, faq: { title: '', items: [] } } as unknown as CmsPage, copy }));
  assert.ok(!empty.includes('Cuéntanos'));
});
test('draft responses never cache or disclose a referrer and cannot be indexed', () => {
  const headers = new Headers();
  protectDraftResponse(headers, true);
  assert.equal(headers.get('Cache-Control'), 'private, no-store');
  assert.equal(headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.equal(headers.get('Referrer-Policy'), 'no-referrer');
  const publicHeaders = new Headers();
  protectDraftResponse(publicHeaders, false);
  assert.equal(publicHeaders.get('Cache-Control'), null);
});
test('home distinguishes unpublished from a publication with every section hidden', () => {
  assert.equal(needsHomeFallback({ sections: [], published_at: null, preview: false }), true);
  assert.equal(needsHomeFallback({ sections: [], published_at: '2026-11-09', preview: false }), false);
  assert.equal(needsHomeFallback({ sections: [], published_at: null, preview: true }), false);
});
