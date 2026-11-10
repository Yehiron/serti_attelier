'use client';

import { focalPosition } from '@/lib/cms-focal';

/* eslint-disable @next/next/no-img-element -- API supplies responsive image renditions. */
import { useEffect, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { HeroSlide, Image } from '@/lib/api/types';
import { heroImages, slideIsEager } from '@/lib/hero-carousel';

const INTERVAL = 6000;
function subscribeViewport(callback: () => void) {
  const query = window.matchMedia('(max-width: 760px)');
  query.addEventListener('change', callback);
  return () => query.removeEventListener('change', callback);
}
function viewport() { return window.matchMedia('(max-width: 760px)').matches ? 'mobile' : 'desktop'; }
function subscribeMotion(callback: () => void) {
  const query = window.matchMedia('(prefers-reduced-motion: reduce)');
  query.addEventListener('change', callback);
  return () => query.removeEventListener('change', callback);
}
function reducedMotion() { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
function subscribeVisibility(callback: () => void) {
  document.addEventListener('visibilitychange', callback);
  return () => document.removeEventListener('visibilitychange', callback);
}
function hidden() { return document.hidden; }

function Sequence({ images, mode, active, stopped, labels }: { images: Image[]; mode: string; active: boolean; stopped: boolean; labels: Dictionary['home']['carousel'] }) {
  const [current, setCurrent] = useState(0);
  const [loaded, setLoaded] = useState<number[]>([]);
  const next = (current + 1) % images.length;
  useEffect(() => {
    if (!active || stopped || images.length < 2) return;
    const timer = window.setTimeout(() => {
      if (loaded.includes(next)) setCurrent(next);
    }, INTERVAL);
    return () => window.clearTimeout(timer);
  }, [active, stopped, images.length, current, next, loaded]);
  return <div className={`hero-sequence hero-slide--${mode}`} aria-hidden={!active}>
    {images.map((image, i) => <img key={i} className={`hero-image hero-slide${active && i === current ? ' is-current' : ''}`} style={{ objectPosition: focalPosition(image) }} src={active ? image.src : undefined} srcSet={active ? image.srcset || undefined : undefined} sizes="100vw" width={image.width} height={image.height} alt={image.alt} aria-hidden={!active || i !== current} loading={active && slideIsEager(i, current, images.length) ? 'eager' : 'lazy'} fetchPriority={i === 0 && active ? 'high' : undefined} onLoad={() => setLoaded(previous => previous.includes(i) ? previous : [...previous, i])} />)}
    {images.length > 1 && <div className="hero-indicators">{images.map((_, i) => <button key={i} type="button" aria-label={labels.goTo.replace('{n}', String(i + 1))} aria-current={current === i ? 'true' : undefined} onClick={() => setCurrent(i)}><span /></button>)}</div>}
  </div>;
}

export function HeroCarousel({ slides, labels, children }: { slides: HeroSlide[]; labels: Dictionary['home']['carousel']; children: ReactNode }) {
  const mode = useSyncExternalStore(subscribeViewport, viewport, () => null);
  const reduced = useSyncExternalStore(subscribeMotion, reducedMotion, () => true);
  const tabHidden = useSyncExternalStore(subscribeVisibility, hidden, () => true);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const desktop = heroImages(slides, false), mobile = heroImages(slides, true);
  const poster = desktop[0] ?? mobile[0];
  return <section className="hero hero-carousel" role="region" aria-roledescription={labels.role} aria-label={labels.label} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onFocusCapture={() => setFocused(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false); }}>
    {/* Server-rendered first slide: one <picture> so the browser fetches only the right image and the
        hero has its photo before hydration (LCP); the sequences take over once the viewport is known. */}
    {mode === null && poster && <picture>{mobile[0] && <source media="(max-width: 760px)" srcSet={mobile[0].srcset || mobile[0].src} sizes="100vw" width={mobile[0].width} height={mobile[0].height} />}<img className="hero-image hero-slide is-current cms-focal-responsive" style={{ '--cms-focal': focalPosition(poster) || '50% 50%', '--cms-mobile-focal': focalPosition(mobile[0] || poster) || '50% 50%' } as CSSProperties} src={poster.src} srcSet={poster.srcset || undefined} sizes="100vw" width={poster.width} height={poster.height} alt={poster.alt} fetchPriority="high" /></picture>}
    <Sequence images={desktop} mode="desktop" active={mode === 'desktop'} stopped={hovered || focused || reduced || tabHidden} labels={labels} />
    <Sequence images={mobile} mode="mobile" active={mode === 'mobile'} stopped={hovered || focused || reduced || tabHidden} labels={labels} />
    {children}
  </section>;
}
