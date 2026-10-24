import type { Alternates, Taxonomy, Taxon } from './api/types.ts';
import { href } from './routes.ts';
import type { Locale } from './i18n.ts';
export type TaxonomyKind = 'category' | 'stone' | 'collection';
export function taxonomyItems(taxonomy: Taxonomy, kind: TaxonomyKind): Taxon[] {
  return kind === 'category' ? taxonomy.categories.flatMap(x => [x, ...x.children]) : kind === 'stone' ? taxonomy.stones : taxonomy.collections;
}
/** The API uses model ordering (position, pk), independent of the locale.
 * Match only complete, structurally identical snapshots; otherwise use home.
 */
export function taxonomyAlternates(kind: TaxonomyKind, locale: Locale, slug: string, source: Taxonomy, target: Taxonomy): Alternates {
  const other = locale === 'es' ? 'en' : 'es';
  const a = taxonomyItems(source, kind), b = taxonomyItems(target, kind);
  const index = a.findIndex(x => x.slug === slug);
  const sameTree = kind !== 'category' || (source.categories.length === target.categories.length && source.categories.every((x,i) => x.children.length === target.categories[i].children.length));
  const translated = a.length === b.length && sameTree && index >= 0 ? b[index] : null;
  return { [locale]: href(kind,locale,slug), [other]: translated ? href(kind,other,translated.slug) : href('home',other) } as Alternates;
}
