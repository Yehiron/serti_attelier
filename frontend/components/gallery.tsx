'use client';
import { useRef, useState } from 'react';
import type { Image } from '@/lib/api/types';
import { Media } from './media';
export function Gallery({ images, label, photo }: { images: Image[]; label: string; photo: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const go = (index: number) => { const target = ref.current?.children[index] as HTMLElement | undefined; target?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest', inline: 'start' }); };
  return <section className="gallery" aria-label={label}><div className="gallery-track" ref={ref} tabIndex={0} onKeyDown={event => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); go(Math.max(0, Math.min(images.length - 1, active + (event.key === 'ArrowRight' ? 1 : -1)))); } }} onScroll={() => { const el = ref.current; if (el) setActive(Math.round(el.scrollLeft / el.clientWidth)); }}>{images.map((image, i) => <div className="gallery-frame" key={`${image.src}-${i}`}><Media image={image} priority={i === 0} sizes="(max-width: 700px) 100vw, 55vw" /></div>)}</div><div className="gallery-thumbs">{images.map((image, i) => <button key={`${image.src}-${i}`} onClick={() => go(i)} aria-label={`${photo} ${i + 1}`} aria-pressed={active === i}><Media image={{ ...image, alt: '' }} sizes="80px" /><span aria-hidden="true">{active === i ? '●' : '○'}</span></button>)}</div></section>;
}
