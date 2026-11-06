'use client';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { Catalog, PieceCard, Taxonomy } from '@/lib/api/types';
import { readResponse } from '@/lib/api/problem';
import { formatCOP } from '@/lib/api/format';
import { href } from '@/lib/routes';
import { Media } from './media';

export function QuickSearch({ locale, dict, taxonomy }: { locale: Locale; dict: Dictionary; taxonomy: Taxonomy }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<{ query: string; pieces: PieceCard[]; error?: boolean } | null>(null);
  const term = query.trim();
  const valid = term.length >= 2;
  const current = result?.query === term ? result : null;
  const all = `${href('search', locale)}?${new URLSearchParams({ q: term })}`;
  useEffect(() => {
    if (!open || term.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({ q: term, page_size: '6', locale });
        const data = await readResponse<Catalog>(await fetch(`/api/v1/catalog/pieces?${params}`, { signal: controller.signal, headers: { Accept: 'application/json' } }));
        if (!controller.signal.aborted) setResult({ query: term, pieces: data.results.slice(0, 6) });
      } catch {
        if (!controller.signal.aborted) setResult({ query: term, pieces: [], error: true });
      }
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [term, open, locale]);
  const close = () => dialog.current?.close();
  return <>
    <Link href={href('search', locale)} aria-label={dict.nav.search} aria-haspopup="dialog" onClick={event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); dialog.current?.showModal(); setOpen(true); input.current?.focus();
    }}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5" /><path d="m15 15 6 6" /></svg></Link>
    <dialog ref={dialog} className="search-dialog" aria-labelledby="quick-search-title" onClose={() => setOpen(false)} onClick={event => { if (event.target === dialog.current) close(); }}>
      <div className="search-dialog-inner"><div className="drawer-heading"><h2 id="quick-search-title">{dict.nav.search}</h2><button type="button" onClick={close} aria-label={dict.nav.close}>×</button></div>
        <form role="search" action={href('search', locale)} method="get" className="search-bar" onSubmit={close}><label className="sr-only" htmlFor="quick-search-q">{dict.ui.query}</label><input ref={input} autoFocus id="quick-search-q" name="q" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={dict.ui.query} maxLength={200} autoComplete="off" /><button className="button">{dict.nav.search}</button></form>
        {!valid ? <div className="search-shortcuts"><div><h3>{dict.ui.category}</h3>{taxonomy.categories.map(category => <Link key={category.slug} href={href('category', locale, category.slug)} onClick={close}>{category.name} ↗</Link>)}</div><div><h3>{dict.nav.stones}</h3>{taxonomy.stones.map(stone => <Link key={stone.slug} href={href('stone', locale, stone.slug)} onClick={close}>{stone.name} ↗</Link>)}</div></div> : <>
          <p className="search-status" role="status">{!current ? dict.ui.loading : current.error ? dict.ui.searchUnavailable : `${current.pieces.length} ${dict.ui.results}`}</p>
          <ul className="search-suggestions">{current?.pieces.map(piece => <li key={piece.sku}><Link href={href('piece', locale, piece.slug)} onClick={close}>{piece.image && <Media image={{ ...piece.image, alt: '' }} sizes="64px" />}<span>{piece.name}<small>{formatCOP((piece.sale_price ?? piece.price).amount_cents, locale)}</small></span><span aria-hidden="true">↗</span></Link></li>)}</ul>
          <Link className="text-link" href={all} onClick={close}>{dict.ui.allSearchResults} ↗</Link>
        </>}
      </div>
    </dialog>
  </>;
}
