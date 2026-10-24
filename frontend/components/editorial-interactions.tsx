'use client';
import { useRef, useState, type ReactNode } from 'react';
import { EditorialTitle } from './editorial-title';
import Link from 'next/link';
import type { StonePanel } from '@/lib/api/types';
import { Media } from './media';
export function StonePanels({ stones, title, subtitle, explore }: { stones: StonePanel[]; title: string; subtitle: string; explore: string }) {
  const [active, setActive] = useState(0);
  return <section className="stone-section"><div className="section-heading"><p className="eyebrow">{subtitle}</p><h2><EditorialTitle text={title} /></h2></div><div className="stone-stage"><div className="stone-backdrops" aria-hidden="true">{stones.map((stone, index) => stone.image && <Media key={stone.slug} image={{ ...stone.image, alt: '' }} className={active === index ? 'active' : ''} sizes="100vw" />)}</div><div className="stone-panels">{stones.map((stone, index) => <Link key={stone.slug} href={stone.href} className="stone-panel" onMouseEnter={() => setActive(index)} onFocus={() => setActive(index)}>{stone.image && <Media image={stone.image} sizes="100vw" />}<div><span className="eyebrow">0{index + 1}</span><h3>{stone.name}</h3><p>{stone.description}</p><span className="text-link">{explore} ↗</span></div></Link>)}</div></div></section>;
}
export function Rail({ children, previous, next }: { children: ReactNode; previous: string; next: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const move = (direction: number) => { const rail = ref.current; rail?.scrollBy({ left: direction * rail.clientWidth * .8, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); };
  return <><div className="rail-controls"><button aria-label={previous} onClick={() => move(-1)}>←</button><button aria-label={next} onClick={() => move(1)}>→</button></div><div className="piece-rail" ref={ref}>{children}</div></>;
}
