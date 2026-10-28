import Link from 'next/link';
import { notFound } from 'next/navigation';
import { locale } from 'next/root-params';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { ApiError, getPiece, getSettings, siteUrl } from '@/lib/api/server';
import { formatCOP, whatsappUrl } from '@/lib/api/format';
import { isLocale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { PageAlternates, pageMetadata } from '@/lib/metadata';
import { AddToCart } from './cart';
import { Gallery } from './gallery';
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
  return pageMetadata(piece.seo.title, piece.seo.description, current, piece.seo.alternates, piece.gallery[0]?.src);
}
export async function PieceDetail({ slug }: { slug: string }) {
  const { piece, current } = await context(slug);
  const [dict, settings] = await Promise.all([getDictionary(), getSettings(current)]);
  const sold = piece.sale_state === 'sold';
  const message = `${sold ? dict.ui.soldMessage : dict.ui.pieceMessage} ${piece.name} (${piece.sku}) · ${new URL(href('piece', current, piece.slug), siteUrl).href}`;
  const general = whatsappUrl(settings.whatsapp.number, message);
  const pageUrl = new URL(href('piece', current, piece.slug), siteUrl).href;
  const wa = (text: string) => whatsappUrl(settings.whatsapp.number, `${text} ${piece.name} (${piece.sku}) · ${pageUrl}`);
  const link = (target: string | null, label: string) => target ? <a className="button" href={target} target="_blank" rel="noopener noreferrer">{label} ↗</a> : <p className="cta-unavailable">{label}</p>;
  // Every state is pre-rendered; LivePieceAction picks the live one (the page itself is cached).
  const variants: Record<SaleState, ReactNode> = {
    available: process.env.NEXT_PUBLIC_CART_ENABLED === 'true' ? <AddToCart sku={piece.sku} locale={current} dict={dict} whatsapp={general} /> : link(wa(dict.ui.pieceMessage), dict.ui.want),
    reserved: link(wa(dict.ui.pieceMessage), dict.ui.reservedCta),
    sold: link(wa(dict.ui.soldMessage), dict.ui.bespoke),
    preorder: link(wa(dict.ui.pieceMessage), dict.ui.preorderCta),
  };
  if (piece.cta.kind === 'whatsapp') variants[piece.sale_state] = link(piece.cta.url, piece.cta.reason === 'sold' ? dict.ui.bespoke : piece.cta.reason === 'reserved' ? dict.ui.reservedCta : dict.ui.preorderCta);
  const notices: Partial<Record<SaleState, ReactNode>> = { reserved: <p className="state-notice">{dict.ui.reservedNotice}</p>, sold: <p className="state-notice">{dict.ui.soldNotice}</p> };
  const activePrice = piece.sale_price ?? piece.price;
  const availability = { available: 'InStock', reserved: 'OutOfStock', sold: 'SoldOut', preorder: 'PreOrder' }[piece.sale_state];
  const jsonld = { '@context': 'https://schema.org', '@type': 'Product', name: piece.name, description: piece.short_description, sku: piece.sku, image: piece.gallery.map(x => new URL(x.src, siteUrl).href), brand: { '@type': 'Brand', name: 'SERTI' }, offers: { '@type': 'Offer', url: piece.seo.alternates[current], price: activePrice.amount_cents / 100, priceCurrency: activePrice.currency, availability: `https://schema.org/${availability}` } };
  const slugFrom = (url: string) => decodeURIComponent(url.split('/').filter(Boolean).at(-1) ?? piece.slug);
  return <main id="main" className="piece-page" data-page-whatsapp={general ?? undefined}><PageAlternates alternates={piece.seo.alternates} /><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld).replace(/</g, '\\u003c') }} /><div className="piece-detail-layout"><Gallery images={piece.gallery.length ? piece.gallery : piece.image ? [piece.image] : []} label={dict.ui.gallery} photo={dict.ui.photo} /><article className="piece-info"><p className="eyebrow">{dict.ui.unique} · {piece.piece_number}</p><div className="piece-title"><h1>{piece.name}</h1><WishButton wish={{ sku: piece.sku, slugs: { es: slugFrom(piece.seo.alternates.es), en: slugFrom(piece.seo.alternates.en) }, name: piece.name, image: piece.image, price: activePrice, addedAt: 0 }} save={dict.ui.save} remove={dict.ui.remove} /></div><p className="piece-price">{piece.sale_price && <del>{formatCOP(piece.price.amount_cents, current)} </del>}{formatCOP(activePrice.amount_cents, current)}</p><p className="body-copy">{piece.short_description}</p><dl className="attributes">{Object.entries(piece.attributes).map(([key, value]) => <div key={key}><dt>{dict.ui.attributeLabels[key as keyof typeof dict.ui.attributeLabels] ?? key}</dt><dd>{String(value ?? '—')}</dd></div>)}</dl><LivePieceAction sku={piece.sku} initial={piece.sale_state} variants={variants} notices={notices} /><p className="shipping-note">{dict.ui.shipping}</p>
      <details><summary>{dict.ui.story}</summary><div className="body-copy whitespace-pre-line">{piece.story || piece.long_description}</div></details><details><summary>{dict.ui.materials}</summary><p>{[...piece.materials, ...piece.stones].map(x => x.name).join(' · ')}</p></details><details><summary>{dict.ui.measurements}</summary><dl className="attributes">{Object.entries(piece.attributes).map(([key, value]) => <div key={key}><dt>{dict.ui.attributeLabels[key as keyof typeof dict.ui.attributeLabels] ?? key}</dt><dd>{String(value ?? '—')}</dd></div>)}</dl></details><details><summary>{dict.ui.care}</summary><p className="whitespace-pre-line">{piece.care}</p></details><details><summary>{dict.ui.shipping} · {dict.ui.returns}</summary><div>{settings.legal_pages.filter(x => x.kind === 'shipping' || x.kind === 'returns').map(x => <Link key={x.kind} className="text-link" href={x.href}>{x.title} ↗</Link>)}</div></details><Link className="text-link" href={href('story', current)}>{dict.ui.manufacturer} ↗</Link>
      </article></div><section className="related"><h2>{dict.ui.related}</h2><div className="piece-grid">{piece.related.map(related => <PieceCard key={related.sku} piece={related} locale={current} dict={dict} />)}</div></section><div className="sticky-piece-cta"><span><span className="sticky-piece-name">{piece.name}</span><small>{formatCOP(activePrice.amount_cents, current)}</small></span><LivePieceAction sku={piece.sku} initial={piece.sale_state} variants={variants} bare /></div></main>;
}
