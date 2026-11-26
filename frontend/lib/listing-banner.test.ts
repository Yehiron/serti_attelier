import { test } from 'node:test';
import { deepStrictEqual, strictEqual } from 'node:assert';
import { listingBannerChips, listingBannerCount } from './listing-banner.ts';

const common = { kind: 'category', base: '/es/joyeria/anillos', query: new URLSearchParams(), children: [], stones: [{ slug: 'ruby', name: 'Rubí' }, { slug: 'opal', name: 'Ópalo' }], facets: [{ slug: 'ruby', count: 2 }, { slug: 'opal', count: 0 }], all: 'Todas', categoryHref: (slug: string) => `/es/joyeria/${slug}` };
test('stone chips preserve filters, toggle selection and reset pagination', () => {
  const query = new URLSearchParams('material=oro&stone=ruby&page=2');
  deepStrictEqual(listingBannerChips({ ...common, query }), [
    { label: 'Todas', href: '/es/joyeria/anillos?material=oro', active: false },
    { label: 'Rubí', href: '/es/joyeria/anillos?material=oro', active: true },
  ]);
  strictEqual(listingBannerChips(common)[1].href, '/es/joyeria/anillos?stone=ruby');
  strictEqual(listingBannerChips({ ...common, query: new URLSearchParams('stone=ruby,opal') })[1].active, false);
  deepStrictEqual(listingBannerChips({ ...common, kind: 'stone' }), []);
});
test('children replace stone chips', () => {
  deepStrictEqual(listingBannerChips({ ...common, children: [{ slug: 'oro', name: 'Oro' }] }), [
    { label: 'Todas', href: common.base, active: true }, { label: 'Oro', href: '/es/joyeria/oro', active: false },
  ]);
});
test('count handles zero, singular and plural in both languages', () => {
  for (const [copy, one, many] of [[{ singular: '1 pieza, única', plural: '{count} piezas, cada una irrepetible' }, '1 pieza, única', '3 piezas, cada una irrepetible'], [{ singular: '1 piece, one of a kind', plural: '{count} pieces, each one of a kind' }, '1 piece, one of a kind', '3 pieces, each one of a kind']] as const) {
    strictEqual(listingBannerCount(0, copy), ''); strictEqual(listingBannerCount(1, copy), one); strictEqual(listingBannerCount(3, copy), many);
  }
});
