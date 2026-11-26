'use client';
import { useRef, type ReactNode } from 'react';
import { EditorialTitle } from './editorial-title';
import Link from 'next/link';
import type { StonePanel } from '@/lib/api/types';
import { Media } from './media';
/* Three fixed photos side by side, each with its stone name over a soft gradient so it stays legible. */
export function StonePanels({ stones, title, subtitle, explore }: { stones: StonePanel[]; title: string; subtitle: string; explore: string }) {
  return <section data-scroll-reveal className="stone-section"><div className="section-heading"><p className="eyebrow">{subtitle}</p><h2><EditorialTitle text={title} /></h2></div><div className="stone-panels">{stones.map((stone, index) => <Link key={stone.slug} href={stone.href} className="stone-panel">{stone.image && <Media image={{ ...stone.image, alt: '' }} sizes="(max-width: 760px) 100vw, 34vw" />}<div><span className="eyebrow">0{index + 1}</span><h3>{stone.name}</h3><span className="text-link">{explore} ↗</span></div></Link>)}</div></section>;
}
export function Rail({ children, previous, next }: { children: ReactNode; previous: string; next: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const move = (direction: number) => { const rail = ref.current; rail?.scrollBy({ left: direction * rail.clientWidth * .8, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); };
  return <><div className="rail-controls"><button className="rail-arrow rail-arrow--prev" aria-label={previous} onClick={() => move(-1)}><svg viewBox="0 0 40 12" aria-hidden="true"><path d="M39 6H2M7 1 2 6l5 5" /></svg></button><button className="rail-arrow rail-arrow--next" aria-label={next} onClick={() => move(1)}><svg viewBox="0 0 40 12" aria-hidden="true"><path d="M1 6h37M33 1l5 5-5 5" /></svg></button></div><div className="piece-rail" ref={ref}>{children}</div></>;
}
