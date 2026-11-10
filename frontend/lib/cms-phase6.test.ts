import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { applyCmsSeo } from './cms-seo.ts';
import { resolveCmsRedirect, redirectPathAllowed } from './cms-redirects.ts';
import { href } from './routes.ts';
import type { CmsMenuItem, CmsSeo } from './api/types.ts';
import type { Locale } from './i18n.ts';

const seo: CmsSeo = { title: '', description: '', image: null, noindex: false };
const base = { title: 'Envíos', description: 'Descripción habitual', alternates: { canonical: '/es/legal/envios', languages: { es: '/es/legal/envios', en: '/en/legal/shipping' } }, openGraph: { title: 'Envíos', description: 'Descripción habitual', url: '/es/legal/envios', locale: 'es_CO' } };

test('metadatos sin SEO conservan literalmente la salida anterior', () => {
  assert.strictEqual(applyCmsSeo(base, undefined, 'https://serti.co'), base);
  assert.strictEqual(applyCmsSeo(base, seo, 'https://serti.co'), base);
});
test('SEO publicado personaliza title, og, twitter y robots; conserva canonical', () => {
  const result = applyCmsSeo(base, { ...seo, title: 'Envíos seguros', description: 'De nuestro taller a tu casa', noindex: true, image: { src: '/media/share.webp', srcset: '', width: 1200, height: 628, alt: 'Taller' } }, 'https://serti.co');
  assert.equal(result.title, 'Envíos seguros');
  assert.equal(result.description, 'De nuestro taller a tu casa');
  assert.deepEqual(result.alternates, base.alternates);
  assert.deepEqual(result.robots, { index: false, follow: true });
  assert.deepEqual(result.openGraph?.images, ['https://serti.co/media/share.webp']);
  assert.ok(result.twitter && 'card' in result.twitter);
  assert.equal(result.twitter.card, 'summary_large_image');
  assert.deepEqual(applyCmsSeo(base, { ...seo, title: 'Borrador' }, 'https://serti.co', true).robots, { index: false, follow: false });
});

test('redirecciones 301 y 308 resuelven cadenas antes de renderizar', () => {
  assert.deepEqual(resolveCmsRedirect('/es/antes', [{ from_path: '/es/antes', to_path: '/es/nueva', status_code: 301 }]), { pathname: '/es/nueva', status: 301 });
  assert.deepEqual(resolveCmsRedirect('/en/old', [{ from_path: '/en/old', to_path: '/en/middle', status_code: 308 }, { from_path: '/en/middle', to_path: '/en/current', status_code: 301 }]), { pathname: '/en/current', status: 308 });
  assert.equal(resolveCmsRedirect('/es/actual', []), null);
});
test('middleware excluye rutas protegidas y rechaza open redirects y bucles', () => {
  for (const path of ['/api/x', '/dashboard/x', '/_next/x', '/media/x', '/static/x', '/preview', '/es/api/x', '/en/dashboard/x', '/es/_next/x', '/en/media/x', '/es/static/x', '/es/preview/x']) assert.equal(redirectPathAllowed(path), false, path);
  for (const target of ['https://evil.test/es/x', '//evil.test', '/es/../x', '/es/%2F%2Fevil.test', '/es/a?url=https://evil.test', '/es/\\evil', '/es/a\n', '/es/a']) assert.equal(resolveCmsRedirect('/es/a', [{ from_path: '/es/a', to_path: target, status_code: 301 }]), null, target);
  assert.equal(resolveCmsRedirect('/es/a', [{ from_path: '/es/a', to_path: '/es/b', status_code: 301 }, { from_path: '/es/b', to_path: '/es/a', status_code: 308 }]), null);
  assert.deepEqual(resolveCmsRedirect('/es/a', [{ from_path: '/es/a', to_path: '/es', status_code: 301 }]), { pathname: '/es', status: 301 });
});

// Compile the real client component locally; replace only app/runtime dependencies.
// This exercises its actual JSX, with React's server renderer and real hooks.
const require = createRequire(import.meta.url);
function loadNavigation(current: Locale) {
  const code = ts.transpileModule(readFileSync(new URL('../components/navigation.tsx', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const mod = { exports: {} as { Navigation: (props: Record<string, unknown>) => React.ReactNode } };
  const stubs: Record<string, unknown> = {
    'next/link': { default: (props: Record<string, unknown>) => h('a', props) },
    'next/navigation': { usePathname: () => `/${current}` },
    '@/lib/routes': { href, routeDecision: (pathname: string) => ({ kind: 'next', pathname }) },
    '@/lib/use-wishlist': { useWishlist: () => ({ wishes: [] }) },
    './cart': { CartUtility: () => null }, './media': { BrandLogo: () => null, Wordmark: () => null },
    './heart': { Heart: () => null }, './flag': { Flag: () => null }, './quick-search': { QuickSearch: () => null },
  };
  Function('require', 'module', 'exports', code)((name: string) => stubs[name] ?? require(name), mod, mod.exports);
  return mod.exports.Navigation;
}
for (const current of ['es', 'en'] as const) test(`migración del menú conserva HTML inicial ${current} y respeta datos publicados`, () => {
  const dict = JSON.parse(readFileSync(new URL(`../app/[locale]/dictionaries/${current}.json`, import.meta.url), 'utf8'));
  const taxonomy = { categories: [{ slug: 'anillos', name: 'Anillos', children: [{ slug: 'oro', name: 'Oro' }] }], stones: [{ slug: 'cuarzo', name: 'Cuarzo' }], collections: [{ slug: 'amanecer', name: 'Amanecer' }] };
  const items: CmsMenuItem[] = [
    { label: dict.nav.catalog, href: href('catalog', current), external: false, dropdown: 'catalog' },
    { label: dict.nav.stones, href: href('catalog', current), external: false, dropdown: 'stones' },
    { label: dict.nav.collections, href: href('catalog', current), external: false, dropdown: 'collections' },
    ...(['personalize', 'story', 'contact'] as const).map(key => ({ label: dict.nav[key], href: href(key, current), external: false, dropdown: null })),
  ];
  const Navigation = loadNavigation(current);
  const render = (published?: CmsMenuItem[]) => renderToStaticMarkup(h(Navigation, { locale: current, dict, taxonomy, items: published }));
  const before = render();
  assert.equal(render(items), before);
  const menu = (key: string, label: string, children: React.ReactNode) => h('details', { 'data-menu': key }, h('summary', {}, label), h('div', {}, children));
  const link = (url: string, text: string, props = {}) => h('a', { ...props, href: url }, text);
  const historical = renderToStaticMarkup(h('nav', {},
    menu('catalog', dict.nav.catalog, [link(href('catalog', current), dict.ui.all), ...taxonomy.categories.map(x => h('div', { key: x.slug }, link(href('category', current, x.slug), x.name), ...x.children.map(c => link(href('category', current, c.slug), c.name, { className: 'subcategory', key: c.slug }))))]),
    menu('stones', dict.nav.stones, taxonomy.stones.map(x => link(href('stone', current, x.slug), x.name, { key: x.slug }))),
    menu('collections', dict.nav.collections, taxonomy.collections.map(x => link(href('collection', current, x.slug), x.name, { key: x.slug }))),
    ...(['personalize', 'story', 'contact'] as const).map(key => link(href(key, current), dict.nav[key], { key })),
  )).replace(/^<nav>|<\/nav>$/g, '');
  assert.equal(before.match(/<nav[^>]*class="desktop-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1], historical);
  assert.match(render([{ label: 'Publicado', href: `/${current}/direccion-publicada`, external: false, dropdown: null }]), new RegExp(`href="/${current}/direccion-publicada"`));
  assert.equal(render([]).match(/<nav[^>]*class="desktop-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1], '');
});
