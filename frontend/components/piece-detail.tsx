import Link from 'next/link';
import { breadcrumbs, productSchema, pieceTitle, pieceDescription, jsonLd } from '@/lib/seo';
import { notFound } from 'next/navigation';
import { locale } from 'next/root-params';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { ApiError, getPiece, getSettings, siteUrl } from '@/lib/api/server';
import { formatCOP } from '@/lib/api/format';
import { isLocale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { PageAlternates, pageMetadata } from '@/lib/metadata';
import { AddToCart } from './cart';
import { Gallery } from './gallery';
import { Media } from './media';
import { collectionLink, pieceEyebrow, stoneColor } from '@/lib/piece-look';
import { PieceCard } from './piece-card';
import { WishButton } from './wish-button';
import type { ReactNode } from 'react';
import { LivePieceAction } from './live-piece-action';
import type { SaleState } from '@/lib/live-state';
async function context(slug: string) {
  const current = await locale(); if (!isLocale(current)) notFound();
  try { const piece = await getPiece(current, slug); return { piece, current }; }
  catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); throw error; }
}
export async function pieceMetadata(slug: string) {
  const { piece, current } = await context(slug);
  return pageMetadata(piece.seo.title || pieceTitle(piece, current), piece.seo.description || pieceDescription(piece, current), current, piece.seo.alternates, piece.gallery[0]?.src);
}
export async function PieceDetail({ slug }: { slug: string }) {
  const { piece, current } = await context(slug);
  const [dict, settings] = await Promise.all([getDictionary(), getSettings(current)]);
  const general = piece.whatsapp_url;
  const pageWhatsapp = piece.sale_state === 'sold' && piece.cta.kind === 'whatsapp' ? piece.cta.url : general;
  const link = (target: string | null, label: string) => target ? <a className="button" href={target} target="_blank" rel="noopener noreferrer">{label} ↗</a> : <p className="cta-unavailable">{label}</p>;
  // Every state is pre-rendered; LivePieceAction picks the live one (the page itself is cached).
  const variants: Record<SaleState, ReactNode> = {
    available: process.env.NEXT_PUBLIC_CART_ENABLED === 'true' ? <AddToCart sku={piece.sku} locale={current} dict={dict} whatsapp={general} /> : link(general, dict.ui.want),
    reserved: link(general, dict.ui.reservedCta),
    sold: link(piece.cta.kind === 'whatsapp' && piece.cta.reason === 'sold' ? piece.cta.url : null, dict.ui.bespoke),
    preorder: link(general, dict.ui.preorderCta),
  };
  if (piece.cta.kind === 'whatsapp') variants[piece.sale_state] = link(piece.cta.url, piece.cta.reason === 'sold' ? dict.ui.bespoke : piece.cta.reason === 'reserved' ? dict.ui.reservedCta : dict.ui.preorderCta);
  const notices: Partial<Record<SaleState, ReactNode>> = { reserved: <p className="state-notice">{dict.ui.reservedNotice}</p>, sold: <p className="state-notice">{dict.ui.soldNotice}</p> };
  const activePrice = piece.sale_price ?? piece.price;
  const jsonld = productSchema(piece, piece.seo.alternates[current], siteUrl, settings.legal_pages.find(x => x.kind === 'returns')?.href);
  const crumbs = breadcrumbs([{ name: 'SERTI', url: href('home', current) }, { name: dict.nav.catalog, url: href('catalog', current) }, { name: piece.name, url: piece.seo.alternates[current] }], siteUrl);
  const story = (piece.story || '').trim();
  const details = (piece.long_description || '').trim();
  const attributeValue = (value: unknown) => typeof value === 'number' ? new Intl.NumberFormat(current, { maximumFractionDigits: 10 }).format(value) : String(value ?? '—');
  const policies = settings.legal_pages.filter(x => x.kind === 'shipping' || x.kind === 'returns');
  const slugFrom = (url: string) => decodeURIComponent(url.split('/').filter(Boolean).at(-1) ?? piece.slug);
  const images = (piece.gallery.length ? piece.gallery : piece.image ? [piece.image] : []).map(image => ({ ...image, alt: image.alt || [piece.name, ...piece.stones.map(x => x.name), ...piece.materials.map(x => x.name)].join(' · ') }));
  const hasGallery = images.length > 1 || !!piece.video;
  const secondary = general ? { available: process.env.NEXT_PUBLIC_CART_ENABLED === 'true' && !(piece.sale_state === 'available' && piece.cta.kind === 'whatsapp') ? <a className="button piece-look-ask" href={general} target="_blank" rel="noopener noreferrer">{dict.ui.lookAsk}</a> : null } : undefined;
  const copy = <div className="piece-look-copy"><p className="piece-look-eyebrow">{[piece.collections[0]?.name || piece.category?.name, piece.sku].filter(Boolean).join(' · ')}</p><h1>{piece.name}</h1><p className="piece-look-price">{piece.sale_price && <del>{formatCOP(piece.price.amount_cents, current)} </del>}{formatCOP(activePrice.amount_cents, current)}</p><div className="piece-look-actions"><LivePieceAction sku={piece.sku} initial={piece.sale_state} variants={variants} notices={notices} secondary={secondary} /><WishButton wish={{ sku: piece.sku, slugs: { es: slugFrom(piece.seo.alternates.es), en: slugFrom(piece.seo.alternates.en) }, name: piece.name, image: piece.image, price: activePrice, addedAt: 0 }} save={dict.ui.save} remove={dict.ui.remove} /></div></div>;
  const photo = (index: number, priority = false) => images[index] && (hasGallery ? <a className="piece-look-photo-link" href="#piece-gallery" aria-label={dict.ui.lookGallery}><Media image={images[index]} priority={priority} /></a> : <Media image={images[index]} priority={priority} />);
  return <main id="main" className="piece-page piece-look" data-page-whatsapp={pageWhatsapp ?? ''}><PageAlternates alternates={piece.seo.alternates} /><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd([jsonld, crumbs]) }} />
    <section className={`piece-look-hero ${images.length === 1 ? 'piece-look-single' : ''} ${!images.length ? 'piece-look-empty' : ''}`}>
      {images.length > 1 && <div className="piece-look-secondary">{photo(1)}</div>}
      {images.length === 1 && <div className="piece-look-panel">{copy}</div>}
      <div className="piece-look-primary">{photo(0, true)}{images.length !== 1 && copy}{hasGallery && <a className="piece-look-gallery-link" href="#piece-gallery">{dict.ui.lookGallery} →</a>}</div>
    </section>
    {hasGallery && <section id="piece-gallery" className="piece-look-gallery" aria-label={dict.ui.gallery}><Gallery images={images} video={piece.video} label={dict.ui.gallery} photo={dict.ui.photo} watch={dict.ui.video} /></section>}
    <section className="piece-look-ficha"><article className="piece-look-story"><p className="eyebrow">{pieceEyebrow(dict.ui.unique, piece.piece_number)}</p><h2>{dict.ui.lookTitle}</h2><p className="piece-look-lede">{piece.short_description}</p>
      {details && <details open><summary>{dict.ui.details}</summary><div className="whitespace-pre-line">{details}</div></details>}{story && <details><summary>{dict.ui.story}</summary><div className="whitespace-pre-line">{story}</div></details>}{piece.care?.trim() && <details><summary>{dict.ui.care}</summary><p className="whitespace-pre-line">{piece.care}</p></details>}{policies.length > 0 && <details><summary>{dict.ui.shipping} · {dict.ui.returns}</summary><div>{policies.map(x => <Link key={x.kind} className="text-link" href={x.href}>{x.title} ↗</Link>)}</div></details>}<Link className="text-link piece-look-workshop" href={href('story', current)}>{dict.ui.manufacturer} ↗</Link>
    </article><div className="piece-look-spec"><img src="/brand/logo/ornament-wine.webp" alt="" width="110" height="41" loading="lazy" /><dl>
      {piece.materials.length > 0 && <div><dt>{dict.ui.lookMetal}</dt><dd>{piece.materials.map(x => x.name).join(' · ')}</dd></div>}
      {piece.stones.length > 0 && <div><dt>{dict.ui.lookStones}</dt><dd>{piece.stones.map((x, i) => <span key={x.slug}>{i > 0 && ' · '}<i className="piece-look-gem" style={{ background: stoneColor(x.name) }} />{x.name}</span>)}</dd></div>}
      {Object.entries(piece.attributes).filter(([key, value]) => value !== null && value !== undefined && String(value).trim() !== '' && !(key === 'metal' && piece.materials.length > 0)).map(([key, value]) => <div key={key}><dt>{dict.ui.attributeLabels[key as keyof typeof dict.ui.attributeLabels] ?? key}</dt><dd>{attributeValue(value)}</dd></div>)}
      {piece.collections.length > 0 && <div><dt>{dict.ui.lookCollections}</dt><dd>{piece.collections.map((x, i) => <span key={x.slug}>{i > 0 && ' · '}<Link href={href('collection', current, x.slug)}>{x.name}</Link></span>)}</dd></div>}
      {piece.category && <div><dt>{dict.ui.lookCategory}</dt><dd><Link href={href('category', current, piece.category.slug)}>{piece.category.name}</Link></dd></div>}{piece.sku && <div><dt>{dict.ui.lookCode}</dt><dd>{piece.sku}</dd></div>}
    </dl></div></section>
    <section className="piece-look-atelier"><div><b>{dict.ui.lookOne}</b><span>{dict.ui.lookOneText}</span></div><div><b>{dict.ui.lookHandmade}</b><span>{dict.ui.lookHandmadeText}</span></div><div><b>{dict.ui.lookShipping}</b><span>{dict.ui.lookShippingText}</span></div></section>
    <section className="piece-look-related"><div className="piece-look-related-head"><h2>{dict.ui.lookRelated}</h2><Link href={collectionLink(current, piece.collections, piece.category)}>{dict.ui.lookViewCollection}</Link></div><div className="piece-grid">{piece.related.map(related => <PieceCard key={related.sku} piece={related} locale={current} dict={dict} />)}</div></section>
    <div className="sticky-piece-cta"><span><span className="sticky-piece-name">{piece.name}</span><small>{formatCOP(activePrice.amount_cents, current)}</small></span><LivePieceAction sku={piece.sku} initial={piece.sale_state} variants={variants} bare /></div></main>;
}
