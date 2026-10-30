import Link from 'next/link';
import { notFound } from 'next/navigation';
import { locale } from 'next/root-params';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { isLocale } from '@/lib/i18n';
import { href, type RouteKey } from '@/lib/routes';
import { getCatalog, getTaxonomy } from '@/lib/api/server';
import { taxonomyAlternates } from '@/lib/taxonomy';
import { catalogQuery, type SearchParams } from '@/lib/catalog';
import { PageAlternates, pageMetadata } from '@/lib/metadata';
import { PieceCard } from './piece-card';
import { FilterSheet } from './filter-sheet';
import { Media } from './media';
export type ListingKind = 'catalog' | 'category' | 'stone' | 'collection' | 'search';
async function context(kind: ListingKind, slug?: string) {
  const current = await locale(); if (!isLocale(current)) notFound();
  const [dict, taxonomy] = await Promise.all([getDictionary(), getTaxonomy(current)]);
  const taxa = kind === 'category' ? taxonomy.categories.flatMap(x => [x, ...x.children]) : kind === 'stone' ? taxonomy.stones : taxonomy.collections;
  const taxon = slug ? taxa.find(x => x.slug === slug) : null;
  if (slug && !taxon) notFound();
  return { current, dict, taxonomy, taxon, title: taxon?.name ?? (kind === 'search' ? dict.nav.search : dict.nav.catalog) };
}
export async function listingMetadata(kind: ListingKind, slug?: string) {
  const { current, dict, title } = await context(kind, slug);
  // Taxonomy model ordering is stable across languages (position, pk).
  const alternates = await listingAlternates(kind, current, slug);
  return pageMetadata(title, dict.meta.description, current, alternates);
}
async function listingAlternates(kind: ListingKind, current: 'es' | 'en', slug?: string) {
  const other = current === 'es' ? 'en' : 'es';
  if (!slug) return { es: href(kind, 'es'), en: href(kind, 'en') };
  const [a, b] = await Promise.all([getTaxonomy(current), getTaxonomy(other)]);
  return taxonomyAlternates(kind as 'category' | 'stone' | 'collection', current, slug, a, b);
}
export async function Listing({ kind, slug, searchParams }: { kind: ListingKind; slug?: string; searchParams: Promise<SearchParams> }) {
  const { current, dict, taxonomy, taxon, title } = await context(kind, slug);
  const params = await searchParams;
  const fixed = slug ? { [kind === 'category' ? 'category' : kind === 'stone' ? 'stone' : 'collection']: slug } : {};
  const query = catalogQuery(params, fixed);
  const data = await getCatalog(current, query.toString());
  const alternates = await listingAlternates(kind, current, slug);
  const base = href(kind as RouteKey, current, slug);
  const stones = query.get('stone')?.split(',') ?? [];
  const form = <form method="get" action={base} className="filter-form"><h2>{dict.ui.filters}</h2>{query.get('q') && <input type="hidden" name="q" value={query.get('q')!} />}{Object.entries(fixed).map(([key, value]) => <input key={key} type="hidden" name={key} value={value} />)}
    {kind !== 'stone' && <fieldset><legend>{dict.ui.stone}</legend>{taxonomy.stones.map(x => <label className="checkbox-label" key={x.slug}><input type="checkbox" name="stone" value={x.slug} defaultChecked={stones.includes(x.slug)} />{x.name}<small>{data.facets.stones.find(f => f.slug === x.slug)?.count ?? 0}</small></label>)}</fieldset>}
    {([['category', taxonomy.categories.flatMap(x => [x, ...x.children])], ['collection', taxonomy.collections], ['material', taxonomy.materials]] as const).map(([key, values]) => !fixed[key] && <label key={key}>{dict.ui[key]}<select name={key} defaultValue={query.get(key) ?? ''}><option value="">{dict.ui.all}</option>{values.map(x => <option key={x.slug} value={x.slug}>{x.name}</option>)}</select></label>)}
    <label>{dict.ui.min}<input type="number" min="0" step="1" name="price_min" defaultValue={query.get('price_min') ?? ''} /></label><label>{dict.ui.max}<input type="number" min="0" step="1" name="price_max" defaultValue={query.get('price_max') ?? ''} /></label>
    <label>{dict.ui.availability}<select name="availability" defaultValue={query.get('availability') ?? 'available'}><option value="available">{dict.ui.now}</option><option value="all">{dict.ui.alsoSold}</option></select></label>
    <label>{dict.ui.sort}<select name="sort" defaultValue={query.get('sort') ?? 'newest'}>{(['newest','price_asc','price_desc','featured'] as const).map((value, i) => <option key={value} value={value}>{[dict.ui.newest,dict.ui.priceAsc,dict.ui.priceDesc,dict.ui.featured][i]}</option>)}</select></label>
    <button className="button" type="submit">{dict.ui.apply}</button><Link className="text-link" href={base}>{dict.ui.clear}</Link></form>;
  const pagination = (page: number) => { const next = new URLSearchParams(query); next.set('page', String(page)); return `${base}?${next}`; };
  const page = Math.max(1, Number(query.get('page') ?? 1));
  const term = query.get('q');
  // On the search page the query box is always visible, not hidden inside the filters.
  const searchBar = kind === 'search' && <form role="search" method="get" action={base} className="search-bar"><label className="sr-only" htmlFor="search-q">{dict.nav.search}</label><input id="search-q" type="search" name="q" defaultValue={term ?? ''} placeholder={dict.ui.query} maxLength={200} /><button className="button" type="submit">{dict.nav.search}</button></form>;
  const empty = kind === 'search' && term ? [dict.ui.noMatches.replace('{query}', term), dict.ui.noMatchesHelp] : [dict.ui.empty, dict.ui.emptyHelp];
  return <main id="main" className="listing-page"><PageAlternates alternates={alternates} /><header className="page-heading"><p className="eyebrow">SERTI · {dict.ui.unique}</p><h1>{title}</h1>{taxon?.cover && <Media className="taxon-cover" image={{ ...taxon.cover, alt: '' }} sizes="(max-width: 1440px) 100vw, 1440px" priority />}{searchBar}<p>{data.count} {dict.ui.results}</p></header><div className="active-filters">{Array.from(query).filter(([key, value]) => !['page','sort','availability'].includes(key) && value && !fixed[key]).map(([key, value]) => { const clean = new URLSearchParams(query); clean.delete(key); return <Link key={key} href={`${base}?${clean}`} aria-label={`${dict.ui.clear}: ${value}`}>{value} ×</Link>; })}</div><div className="listing-layout"><aside className="desktop-filters">{form}</aside><section className="listing-results" aria-label={title}><h2 className="sr-only">{title} · {dict.ui.results}</h2><FilterSheet label={dict.ui.filters} close={dict.nav.close}>{form}</FilterSheet><noscript><div className="noscript-filters">{form}</div></noscript>{data.results.length ? <div className="piece-grid">{data.results.map(piece => <PieceCard key={piece.sku} piece={piece} locale={current} dict={dict} />)}</div> : <div className="empty-state"><h2>{empty[0]}</h2><p>{empty[1]}</p><Link className="text-link" href={href('catalog', current)}>{dict.ui.explore} ↗</Link></div>}{(data.previous || data.next) && <nav className="pagination" aria-label={dict.ui.results}>{data.previous && <Link href={pagination(page - 1)}>{dict.ui.previous}</Link>}<span aria-current="page">{page}</span>{data.next && <Link href={pagination(page + 1)}>{dict.ui.next}</Link>}</nav>}</section></div></main>;
}
