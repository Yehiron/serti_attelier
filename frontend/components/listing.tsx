import Link from 'next/link';
import { Fragment } from 'react';
import { notFound } from 'next/navigation';
import { locale } from 'next/root-params';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { isLocale } from '@/lib/i18n';
import { href, type RouteKey } from '@/lib/routes';
import { getCatalog, getTaxonomy } from '@/lib/api/server';
import { taxonomyAlternates } from '@/lib/taxonomy';
import { catalogQuery, type SearchParams } from '@/lib/catalog';
import { formatCOP } from '@/lib/api/format';
import { centsToPesos, priceBounds } from '@/lib/price-range';
import { PageAlternates, pageMetadata } from '@/lib/metadata';
import { PieceCard } from './piece-card';
import { FilterSelect, type FilterOption } from './filter-select';
import { PriceRange } from './price-range';
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
  // Option lists shared by the enhanced rows and the no-JS native selects.
  const optionSets: { key: 'category' | 'collection' | 'material' | 'availability' | 'sort'; fallback: string; options: FilterOption[] }[] = [
    { key: 'category', fallback: '', options: [{ value: '', label: dict.ui.all }, ...taxonomy.categories.flatMap(x => [{ value: x.slug, label: x.name }, ...x.children.map(child => ({ value: child.slug, label: child.name, child: true }))])] },
    { key: 'collection', fallback: '', options: [{ value: '', label: dict.ui.all }, ...taxonomy.collections.map(x => ({ value: x.slug, label: x.name }))] },
    { key: 'material', fallback: '', options: [{ value: '', label: dict.ui.all }, ...taxonomy.materials.map(x => ({ value: x.slug, label: x.name }))] },
    { key: 'availability', fallback: 'available', options: [{ value: 'available', label: dict.ui.now }, { value: 'all', label: dict.ui.alsoSold }] },
    { key: 'sort', fallback: 'newest', options: (['newest', 'price_asc', 'price_desc', 'featured'] as const).map((value, i) => ({ value, label: [dict.ui.newest, dict.ui.priceAsc, dict.ui.priceDesc, dict.ui.featured][i] })) },
  ];
  const visibleSets = optionSets.filter(set => !(set.key in fixed));
  const bounds = priceBounds(data.facets.price.min_cents, data.facets.price.max_cents);
  // catalogQuery keeps prices in cents; the form works in pesos.
  const priceMin = centsToPesos(query.get('price_min'));
  const priceMax = centsToPesos(query.get('price_max'));
  const select = (set: (typeof optionSets)[number], enhanced: boolean) => enhanced
    ? <FilterSelect key={set.key} name={set.key} label={dict.ui[set.key]} options={set.options} defaultValue={query.get(set.key) ?? set.fallback} />
    : <label key={set.key}>{dict.ui[set.key]}<select name={set.key} defaultValue={query.get(set.key) ?? set.fallback}>{set.options.map(o => <option key={o.value} value={o.value}>{o.child ? `— ${o.label}` : o.label}</option>)}</select></label>;
  const price = (enhanced: boolean) => enhanced && bounds
    ? <PriceRange key="price" bounds={bounds} initialMin={priceMin} initialMax={priceMax} locale={current} label={dict.ui.price} minLabel={dict.ui.min} maxLabel={dict.ui.max} />
    : <><label>{dict.ui.min}<input type="number" min="0" step="1" name="price_min" placeholder={dict.ui.priceFrom} defaultValue={priceMin ?? ''} /></label><label>{dict.ui.max}<input type="number" min="0" step="1" name="price_max" placeholder={dict.ui.priceTo} defaultValue={priceMax ?? ''} /></label></>;
  // The no-JS copy (noscript) keeps native controls so filtering always works.
  const filterForm = (enhanced: boolean) => {
    const rows = [
      kind !== 'stone' && <fieldset key="stone"><legend>{dict.ui.stone}</legend>{taxonomy.stones.map(x => <label className="checkbox-label" key={x.slug}><input type="checkbox" name="stone" value={x.slug} defaultChecked={stones.includes(x.slug)} />{x.name}<small>{data.facets.stones.find(f => f.slug === x.slug)?.count ?? 0}</small></label>)}</fieldset>,
      ...visibleSets.filter(set => set.key !== 'availability' && set.key !== 'sort').map(set => select(set, enhanced)),
      <Fragment key="price">{price(enhanced)}</Fragment>,
      ...visibleSets.filter(set => set.key === 'availability' || set.key === 'sort').map(set => select(set, enhanced)),
    ].filter(Boolean);
    const actions = <Fragment key="actions"><button className="button" type="submit">{dict.ui.apply}</button><Link className="text-link" href={base}>{dict.ui.clear}</Link></Fragment>;
    // Panel rows go in three independent columns, so an unfolded list only pushes its own column.
    const size = Math.ceil(rows.length / 3);
    const columns = [0, 1, 2].map(i => rows.slice(i * size, (i + 1) * size));
    return <form method="get" action={base} className="filter-form"><h2>{dict.ui.filters}</h2>{query.get('q') && <input type="hidden" name="q" value={query.get('q')!} />}{Object.entries(fixed).map(([key, value]) => <input key={key} type="hidden" name={key} value={value} />)}
      {enhanced ? columns.map((column, i) => <div key={i} className="filter-col">{column}{i === 2 && actions}</div>) : <>{rows}{actions}</>}</form>;
  };
  const pagination = (page: number) => { const next = new URLSearchParams(query); next.set('page', String(page)); return `${base}?${next}`; };
  const page = Math.max(1, Number(query.get('page') ?? 1));
  const term = query.get('q');
  // On the search page the query box is always visible, not hidden inside the filters.
  const searchBar = kind === 'search' && <form role="search" method="get" action={base} className="search-bar"><label className="sr-only" htmlFor="search-q">{dict.nav.search}</label><input id="search-q" type="search" name="q" defaultValue={term ?? ''} placeholder={dict.ui.query} maxLength={200} /><button className="button" type="submit">{dict.nav.search}</button></form>;
  const empty = kind === 'search' && term ? [dict.ui.noMatches.replace('{query}', term), dict.ui.noMatchesHelp] : [dict.ui.empty, dict.ui.emptyHelp];
  const activeFilters = Array.from(query).filter(([key, value]) => !['page', 'sort', 'availability'].includes(key) && value && !fixed[key]);
  const activeCount = activeFilters.reduce((total, [key, value]) => total + (key === 'stone' ? value.split(',').length : 1), 0);
  // Capsule toggle (native details: opens and closes without JavaScript, announced as expanded/collapsed).
  const filterPanel = <details className="filter-panel"><summary className="filter-pill"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 6h9M15 6h2M3 14h2M8 14h9" /><circle cx="13.5" cy="6" r="1.8" /><circle cx="6.5" cy="14" r="1.8" /></svg>{dict.ui.filters}{activeCount > 0 && <span className="filter-count" aria-label={`${activeCount} ${dict.ui.activeFilters}`}>{activeCount}</span>}</summary><div className="filter-panel-body">{filterForm(true)}</div></details>;
  return <main id="main" className="listing-page"><PageAlternates alternates={alternates} /><header className="page-heading"><p className="eyebrow">SERTI · {dict.ui.unique}</p><h1>{title}</h1>{kind !== 'stone' && taxon?.cover && <Media className="taxon-cover" image={{ ...taxon.cover, alt: '' }} sizes="(max-width: 1440px) 100vw, 1440px" priority />}{searchBar}<p>{data.count} {dict.ui.results}</p></header>{filterPanel}<div className="active-filters">{activeFilters.map(([key, value]) => { const clean = new URLSearchParams(query); clean.delete(key); const shown = key === 'price_min' || key === 'price_max' ? `${key === 'price_min' ? dict.ui.priceAbove : dict.ui.priceBelow} ${formatCOP(Number(value), current)}` : value; return <Link key={key} href={`${base}?${clean}`} aria-label={`${dict.ui.clear}: ${shown}`}>{shown} ×</Link>; })}</div><section className="listing-results" aria-label={title}><h2 className="sr-only">{title} · {dict.ui.results}</h2><noscript><div className="noscript-filters">{filterForm(false)}</div></noscript>{data.results.length ? <div className="piece-grid">{data.results.map(piece => <PieceCard key={piece.sku} piece={piece} locale={current} dict={dict} />)}</div> : <div className="empty-state"><h2>{empty[0]}</h2><p>{empty[1]}</p><Link className="text-link" href={href('catalog', current)}>{dict.ui.explore} ↗</Link></div>}{(data.previous || data.next) && <nav className="pagination" aria-label={dict.ui.results}>{data.previous && <Link href={pagination(page - 1)}>{dict.ui.previous}</Link>}<span aria-current="page">{page}</span>{data.next && <Link href={pagination(page + 1)}>{dict.ui.next}</Link>}</nav>}</section></main>;
}
