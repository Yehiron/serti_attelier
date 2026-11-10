import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { createElement as h, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import type { Dictionary } from '../app/[locale]/dictionaries';
import type { CmsMenuItem, Settings } from './api/types.ts';
import type { Locale } from './i18n.ts';
import { href } from './routes.ts';

const require = createRequire(import.meta.url);
const source = ts.transpileModule(readFileSync(new URL('../components/site-shell.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

// Render the real async Footer; replace only framework/API boundaries.
async function renderFooter(locale: Locale, settings: Settings, published?: CmsMenuItem[]) {
  const dict: Dictionary = JSON.parse(readFileSync(new URL(`../app/[locale]/dictionaries/${locale}.json`, import.meta.url), 'utf8'));
  const mod = { exports: {} as { Footer: (props: { locale: Locale; dict: Dictionary }) => Promise<ReactNode> } };
  const stubs: Record<string, unknown> = {
    'next/link': { default: (props: Record<string, unknown>) => h('a', props) },
    'next/headers': { draftMode: async () => ({ isEnabled: false }) },
    '@/lib/api/server': {
      getSettings: async () => settings,
      getMenu: async () => {
        if (published === undefined) throw new Error('Sin publicación disponible');
        return { items: published, preview: false };
      },
      getCopyrightYear: async () => 2026,
      getTaxonomy: async () => ({ categories: [], stones: [], collections: [] }),
      siteUrl: 'https://serti.co', emptySettings: settings,
    },
    '@/lib/routes': { href },
    './navigation': { Navigation: () => null },
    './media': { Signature: () => h('span', {}, 'Firma') },
    './whatsapp': { FloatingWhatsApp: () => null },
    './social-links': { SocialLinks: () => null },
    './payment-methods': { PaymentMethods: () => h('span', {}, 'Medios de pago') },
  };
  Function('require', 'module', 'exports', source)((name: string) => stubs[name] ?? require(name), mod, mod.exports);
  return renderToStaticMarkup(await mod.exports.Footer({ locale, dict }));
}

for (const locale of ['es', 'en'] as const) {
  const settings: Settings = {
    title_scale: 1, text_scale: 1, whatsapp: { number: null, general_url: null },
    social: [], support_email: 'hola@serti.co',
    legal_pages: [
      { kind: 'terms', title: locale === 'es' ? 'Términos y condiciones' : 'Terms and conditions', href: `/${locale}/legal/${locale === 'es' ? 'terminos' : 'terms'}` },
      { kind: 'shipping', title: locale === 'es' ? 'Envíos' : 'Shipping', href: `/${locale}/legal/${locale === 'es' ? 'envios' : 'shipping'}` },
    ],
  };
  test(`pie ${locale}: menú inicial conserva todo el HTML anterior`, async () => {
    const initial: CmsMenuItem[] = settings.legal_pages.map(page => ({ label: page.title, href: page.href, external: false, dropdown: null }));
    assert.equal(await renderFooter(locale, settings, initial), await renderFooter(locale, settings));
  });
  test(`pie ${locale}: publicación vacía no repone enlaces legales`, async () => {
    const html = await renderFooter(locale, settings, []);
    assert.equal(html.match(/<nav[^>]*>([\s\S]*?)<\/nav>/)?.[1], '');
    assert.ok(!html.includes(settings.legal_pages[0].href));
    assert.ok(html.includes(`href="${href('personalize', locale)}"`));
  });
  test(`pie ${locale}: enlace externo conserva destino y protección`, async () => {
    const html = await renderFooter(locale, settings, [{ label: 'SERTI en prensa', href: 'https://example.com/serti', external: true, dropdown: null }]);
    assert.match(html, /<nav[^>]*><a href="https:\/\/example.com\/serti" target="_blank" rel="noopener noreferrer">SERTI en prensa<\/a><\/nav>/);
    assert.ok(!html.includes(settings.legal_pages[0].href));
  });
}
