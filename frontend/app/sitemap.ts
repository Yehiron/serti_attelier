import { largestImage } from '@/lib/seo';
import type { MetadataRoute } from 'next';
import { connection } from 'next/server';
import { getCatalog, getPiece, getTaxonomy, getPublishedPageByKind, ApiError, siteUrl } from '@/lib/api/server';
import { href, type RouteKey } from '@/lib/routes';
import { taxonomyAlternates, taxonomyItems } from '@/lib/taxonomy';
import { locales } from '@/lib/i18n';
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Built per request (each API read below is cached), never at build time.
  await connection();
  const entries = new Map<string, MetadataRoute.Sitemap[number]>();
  const add = (url: string, languages?: { es: string; en: string }, lastModified?: string, images?: string[]) => { const absolute = new URL(url, siteUrl).href; entries.set(absolute, { url: absolute, ...(lastModified ? { lastModified } : {}), ...(images?.length ? { images } : {}), ...(languages ? { alternates: { languages: { es: new URL(languages.es, siteUrl).href, en: new URL(languages.en, siteUrl).href } } } : {}) }); };
  for (const key of ['home','catalog'] as RouteKey[]) { const languages = { es: href(key,'es'), en: href(key,'en') }; for (const value of Object.values(languages)) add(value, languages); }
  // Fail rather than cache an incomplete sitemap if the API is unavailable.
  const [esTaxonomy, enTaxonomy] = await Promise.all([getTaxonomy('es'), getTaxonomy('en')]);
  for (const current of locales) {
    const taxonomy = current === 'es' ? esTaxonomy : enTaxonomy;
    const otherTaxonomy = current === 'es' ? enTaxonomy : esTaxonomy;

    for (const key of ['category', 'stone', 'collection'] as const) {
      for (const item of taxonomyItems(taxonomy, key)) {
        const alternates = taxonomyAlternates(key, current, item.slug, taxonomy, otherTaxonomy);
        // A home fallback is useful for navigation, but isn't an SEO equivalent.
        if (alternates.es !== '/es' && alternates.en !== '/en') add(href(key, current, item.slug), alternates, item.updated_at ?? undefined);
        else add(href(key, current, item.slug), undefined, item.updated_at ?? undefined);
      }
    }
    for (const kind of ['terms', 'privacy', 'returns', 'shipping', 'cookies', 'manufacturer', 'contact', 'personalize']) {
      try {
        const page = await getPublishedPageByKind(current, kind);
        if (!page.seo?.noindex) add(page.alternates[current], page.alternates, page.updated_at);
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) throw error;
        const route = { manufacturer: 'story', personalize: 'personalize', contact: 'contact' }[kind] as RouteKey | undefined;
        if (route) { const languages = { es: href(route, 'es'), en: href(route, 'en') }; add(languages[current], languages); }
      }
    }
    let page = 1;
    while (true) {
      const catalog = await getCatalog(current, `availability=all&page_size=48&page=${page}`);
      const details = await Promise.all(catalog.results.map(piece => getPiece(current,piece.slug)));
      for (const piece of details) add(piece.seo.alternates[current],piece.seo.alternates, piece.updated_at ?? piece.published_at ?? undefined, piece.gallery.map(image => new URL(largestImage(image), siteUrl).href));
      if (!catalog.next) break; page++;
    }
  }
  return [...entries.values()];
}
