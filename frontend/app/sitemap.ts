import type { MetadataRoute } from 'next';
import { connection } from 'next/server';
import { getCatalog, getPiece, getSettings, getTaxonomy, getPublishedPage, siteUrl } from '@/lib/api/server';
import { href, type RouteKey } from '@/lib/routes';
import { taxonomyAlternates, taxonomyItems } from '@/lib/taxonomy';
import { locales } from '@/lib/i18n';
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Built per request (each API read below is cached), never at build time.
  await connection();
  const entries = new Map<string, MetadataRoute.Sitemap[number]>();
  const add = (url: string, languages?: { es: string; en: string }) => { const absolute = new URL(url, siteUrl).href; entries.set(absolute, { url: absolute, ...(languages ? { alternates: { languages: { es: new URL(languages.es, siteUrl).href, en: new URL(languages.en, siteUrl).href } } } : {}) }); };
  for (const key of ['home','catalog','personalize','story','contact'] as RouteKey[]) { const languages = { es: href(key,'es'), en: href(key,'en') }; for (const value of Object.values(languages)) add(value, languages); }
  // Fail rather than cache an incomplete sitemap if the API is unavailable.
  const [esTaxonomy, enTaxonomy] = await Promise.all([getTaxonomy('es'), getTaxonomy('en')]);
  for (const current of locales) {
    const taxonomy = current === 'es' ? esTaxonomy : enTaxonomy;
    const otherTaxonomy = current === 'es' ? enTaxonomy : esTaxonomy;
    const settings = await getSettings(current);
    for (const key of ['category', 'stone', 'collection'] as const) {
      for (const item of taxonomyItems(taxonomy, key)) {
        const alternates = taxonomyAlternates(key, current, item.slug, taxonomy, otherTaxonomy);
        // A home fallback is useful for navigation, but isn't an SEO equivalent.
        if (alternates.es !== '/es' && alternates.en !== '/en') add(href(key, current, item.slug), alternates);
        else add(href(key, current, item.slug));
      }
    }
    const legalPages = await Promise.all(settings.legal_pages.map(page => {
      const slug = decodeURIComponent(page.href.split('/').filter(Boolean).at(-1)!);
      return getPublishedPage(current, slug);
    }));
    for (const page of legalPages) add(page.alternates[current], page.alternates);
    let page = 1;
    while (true) {
      const catalog = await getCatalog(current, `availability=all&page_size=48&page=${page}`);
      const details = await Promise.all(catalog.results.map(piece => getPiece(current,piece.slug)));
      for (const piece of details) add(piece.seo.alternates[current],piece.seo.alternates);
      if (!catalog.next) break; page++;
    }
  }
  return [...entries.values()];
}
