'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { LiveState } from '@/lib/api/types';
import { useWishlist } from '@/lib/use-wishlist';
import { getStatuses } from '@/lib/api/client';
import { formatCOP, whatsappUrl } from '@/lib/api/format';
import { href } from '@/lib/routes';
import { Media } from './media';
export function WishlistPage({ locale, dict, number }: { locale: Locale; dict: Dictionary; number: string | null }) {
  const { wishes, toggle } = useWishlist();
  const [status, setStatus] = useState<Record<string, LiveState>>({});
  const [error, setError] = useState(false);
  const skus = wishes.map(x => x.sku).sort().join(',');
  useEffect(() => {
    if (!skus) return;
    const controller = new AbortController();
    const refresh = () => getStatuses(skus.split(','), controller.signal).then(value => { setStatus(value); setError(false); }).catch(() => { if (!controller.signal.aborted) setError(true); });
    void refresh(); const timer = window.setInterval(refresh, 60000); window.addEventListener('focus', refresh);
    return () => { controller.abort(); clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [skus]);
  if (!wishes.length) return <section className="empty-state"><h2>{dict.ui.wishlistEmpty}</h2><p>{dict.ui.wishlistHelp}</p><Link className="text-link" href={href('catalog', locale)}>{dict.ui.explore} ↗</Link></section>;
  return <><p>{dict.ui.wishPrivacy}</p>{error && <p role="status">{dict.ui.statusError}</p>}<div className="piece-grid wishlist-grid">{wishes.map(wish => {
    const state = status[wish.sku]; const url = whatsappUrl(number, `${dict.ui.soldMessage} ${wish.name} (${wish.sku})`);
    return <article className="piece-card" key={wish.sku}><Link className="piece-photo" href={href('piece', locale, wish.slugs[locale])}>{wish.image ? <Media image={wish.image} sizes="(max-width:700px) 45vw, 30vw" /> : <span className="image-placeholder">{dict.ui.image}</span>}</Link><div className="card-caption"><h2><Link href={href('piece', locale, wish.slugs[locale])}>{wish.name}</Link></h2><p>{formatCOP(wish.price.amount_cents, locale)}</p></div><p aria-live="polite">{state ? dict.ui[state] : dict.ui.statusLoading}</p>{state === 'sold' && (url ? <a className="text-link" href={url} target="_blank" rel="noopener noreferrer">{dict.ui.bespoke} ↗</a> : <p>{dict.ui.bespoke}</p>)}<button className="text-link" onClick={() => toggle(wish)}>{dict.ui.remove} ×</button></article>;
  })}</div></>;
}
