import { supportedSections } from '@/lib/section-compat';
import { needsHomeFallback } from '@/lib/cms-preview';
import { locale } from 'next/root-params';
import { getDictionary } from './dictionaries';
import { getHome, getCatalog, getTaxonomy } from '@/lib/api/server';
import type { Section } from '@/lib/api/types';
import { isLocale } from '@/lib/i18n';
import { notFound } from 'next/navigation';
import { href } from '@/lib/routes';
import { HomeSection } from '@/components/home-sections';
import { pageMetadata, PageAlternates } from '@/lib/metadata';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() {
  const current = await locale(); if (!isLocale(current)) notFound(); const dict = await getDictionary();
  return pageMetadata(dict.meta.title, dict.meta.description, current, { es: '/es', en: '/en' });
}
export default async function Home() {
  const current = await locale(); if (!isLocale(current)) notFound();
  const dict = await getDictionary();
  const home = await getHome(current);
  let sections = supportedSections(home.sections);
  if (needsHomeFallback(home)) {
    const [taxonomy, catalog] = await Promise.all([getTaxonomy(current), getCatalog(current, 'sort=newest&page_size=8')]);
    sections = [
      { id: 'hero', kind: 'hero', schema_version: 1, title: dict.home.title.join('\n'), subtitle: dict.home.lede, image: null, cta: { label: dict.ui.explore, href: href('catalog', current), external: false } },
      { id: 'statement', kind: 'statement', schema_version: 1, title: dict.home.statement, body: dict.home.statementBody },
      { id: 'stones', kind: 'stone_panels', schema_version: 1, title: dict.home.stones, subtitle: dict.home.stonesSubtitle, stones: taxonomy.stones.map(x => ({ ...x, description: '', image: x.cover_image ? { src: x.cover_image, srcset: '', width: 2400, height: 1350, alt: x.name } : null, href: href('stone', current, x.slug) })) },
      { id: 'new', kind: 'collection_rail', schema_version: 1, title: dict.home.newest, subtitle: dict.home.newestSubtitle, collection: { slug: '', name: dict.nav.catalog, href: href('catalog', current) }, pieces: catalog.results },
      { id: 'story', kind: 'story', schema_version: 1, title: dict.home.storyTitle, body: dict.home.storyBody, image: null, cta: { label: dict.nav.story, href: href('story', current), external: false } },
      { id: 'personalize', kind: 'personalize', schema_version: 1, title: dict.home.customTitle, body: dict.home.customBody, image: null, cta: { label: dict.nav.personalize, href: href('personalize', current), external: false } },
    ] satisfies Section[];
  }
  const firstHero = sections.find(x => x.kind === 'hero')?.id;
  return <main id="main" className="home-page"><PageAlternates alternates={{ es: '/es', en: '/en' }} />{firstHero === undefined && <h1 className="sr-only">{dict.meta.title}</h1>}{sections.map(section => <HomeSection key={section.id} section={section} locale={current} dict={dict} firstHero={section.id === firstHero} />)}</main>;
}
