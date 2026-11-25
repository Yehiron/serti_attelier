import Link from 'next/link';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { Alternates, PieceCard as Card } from '@/lib/api/types';
import { formatCOP } from '@/lib/api/format';
import { href } from '@/lib/routes';
import { Media } from './media';
import { WishButton } from './wish-button';
export async function PieceCard({ piece, locale, dict, alternates }: { piece: Card; locale: Locale; dict: Dictionary; alternates?: Alternates }) {
  alternates ??= piece.alternates;
  const sizes = '(max-width: 700px) 45vw, (max-width: 1100px) 30vw, 23vw';
  const slug = (path: string) => decodeURIComponent(path.split('/').filter(Boolean).at(-1) ?? piece.slug);
  return <article className="piece-card">
    <div className="piece-photo"><Link href={href('piece', locale, piece.slug)} aria-label={piece.name}>{piece.image ? <Media image={{ ...piece.image, alt: piece.image.alt || [piece.name, ...piece.stones.map(x => x.name)].join(' · ') }} sizes={sizes} /> : <span className="image-placeholder">{dict.ui.image}</span>}
      {/* Desktop-only alternate view; lazy, so it loads with the card and is ready before hover. */}
      {piece.image && piece.hover_image && <Media className="hover-image" image={{ ...piece.hover_image, alt: '' }} sizes={sizes} />}</Link>
    <WishButton wish={{ sku: piece.sku, slugs: { es: alternates ? slug(alternates.es) : piece.slug, en: alternates ? slug(alternates.en) : piece.slug }, name: piece.name, image: piece.image, price: piece.sale_price ?? piece.price, addedAt: 0 }} save={dict.ui.save} remove={dict.ui.remove} /></div>
    <div className="card-caption"><h3><Link href={href('piece', locale, piece.slug)}>{piece.name}</Link></h3><p>{piece.sale_price && <del>{formatCOP(piece.price.amount_cents, locale)} </del>}{formatCOP((piece.sale_price ?? piece.price).amount_cents, locale)}</p></div>
    <p className="badge">{dict.ui.unique}{piece.sale_state !== 'available' ? ` · ${dict.ui[piece.sale_state]}` : piece.is_new ? ` · ${dict.ui.new}` : ''}</p>
  </article>;
}
