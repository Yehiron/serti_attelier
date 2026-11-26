import Link from 'next/link';
import { cache } from 'react';
import { getDictionary } from '@/app/[locale]/dictionaries';
import { getCatalog, getSettings } from '@/lib/api/server';
import { whatsappUrl } from '@/lib/api/format';
import type { Locale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { PieceCard } from './piece-card';

const suggestions = cache(async (locale: Locale) => (await getCatalog(locale, 'page_size=48')).results.filter(piece => piece.sale_state === 'available').slice(0, 4));

export async function NotFoundContent({ locale, kind = 'page' }: { locale: Locale; kind?: 'piece' | 'page' }) {
  const es = locale === 'es';
  const [dict, pieces, settings] = await Promise.all([getDictionary(), suggestions(locale).catch(() => []), getSettings(locale).catch(() => null)]);
  const whatsapp = whatsappUrl(settings?.whatsapp.number ?? null, es ? 'Hola, quisiera conocer sus joyas.' : 'Hello, I would like to learn about your jewelry.');
  return <main id="main">
    <section className="error-page wine"><div className="error-inner">
      <p className="eyebrow">SERTI · 404</p>
      <h1>{kind === 'piece' ? (es ? 'Esta joya encontró otro destino' : 'This piece has found another home') : (es ? 'Esta página no está en el atelier' : "This page isn't in the atelier")}</h1>
      <p>{es ? 'Te invitamos a descubrir las piezas y las historias que hemos creado para ti.' : 'Discover the pieces and stories we have created for you.'}</p>
      <div className="error-actions"><Link className="button" href={href('home', locale)}>{es ? 'Volver al inicio' : 'Return home'}</Link><Link className="error-secondary" href={href('catalog', locale)}>{es ? 'Explorar joyería' : 'Explore jewelry'} ↗</Link>{whatsapp && <a className="error-secondary" href={whatsapp} target="_blank" rel="noopener noreferrer">WhatsApp ↗</a>}</div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="error-ornament" src="/brand/logo/ornament-gold.webp" alt="" />
    </div></section>
    {pieces.length > 0 && <section className="error-suggestions"><p className="eyebrow">SERTI · {es ? 'Piezas únicas' : 'Unique pieces'}</p><h2>{es ? 'Otras joyas por descubrir' : 'More pieces to discover'}</h2><div className="piece-grid">{pieces.map(piece => <PieceCard key={piece.sku} piece={piece} locale={locale} dict={dict} />)}</div></section>}
  </main>;
}
