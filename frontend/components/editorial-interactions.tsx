'use client';
import { useRef, type ReactNode } from 'react';
import { EditorialTitle } from './editorial-title';
import Link from 'next/link';
import type { StonePanel } from '@/lib/api/types';
import { Media } from './media';
/* Three fixed photos side by side, each with its stone name over a soft gradient so it stays legible. */
export function StonePanels({ stones, title, subtitle, explore }: { stones: StonePanel[]; title: string; subtitle: string; explore: string }) {
  return <section className="stone-section"><div className="section-heading"><p className="eyebrow">{subtitle}</p><h2><EditorialTitle text={title} /></h2></div><div className="stone-panels">{stones.map((stone, index) => <Link key={stone.slug} href={stone.href} className="stone-panel">{stone.image && <Media image={{ ...stone.image, alt: '' }} sizes="(max-width: 760px) 100vw, 34vw" />}<div><span className="eyebrow">0{index + 1}</span><h3>{stone.name}</h3><span className="text-link">{explore} ↗</span></div></Link>)}</div></section>;
}
export function Rail({ children, previous, next }: { children: ReactNode; previous: string; next: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const move = (direction: number) => { const rail = ref.current; rail?.scrollBy({ left: direction * rail.clientWidth * .8, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); };
  return <><div className="rail-controls"><button aria-label={previous} onClick={() => move(-1)}>←</button><button aria-label={next} onClick={() => move(1)}>→</button></div><div className="piece-rail" ref={ref}>{children}</div></>;
}
