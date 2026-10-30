'use client';
import { useEffect, useRef, useState } from 'react';
import type { Image, PieceVideo } from '@/lib/api/types';
import { Media } from './media';
type Slide = { kind: 'image'; image: Image } | { kind: 'video'; video: PieceVideo };
/** Calm mode: no autoplay with reduced motion or the browser's data saver. */
function calm() {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches || !!connection?.saveData;
}
export function Gallery({ images, video, label, photo, watch }: { images: Image[]; video?: PieceVideo | null; label: string; photo: string; watch: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const player = useRef<HTMLVideoElement>(null);
  const [active, setActive] = useState(0);
  // The video goes right after the main photo.
  const slides: Slide[] = images.map(image => ({ kind: 'image', image }));
  const videoIndex = video ? Math.min(1, slides.length) : -1;
  if (video) slides.splice(videoIndex, 0, { kind: 'video', video });
  useEffect(() => {
    const el = player.current;
    if (!el) return;
    // preload="none": nothing is downloaded until the visitor reaches the video.
    if (active === videoIndex && !calm()) void el.play().catch(() => {});
    else el.pause();
  }, [active, videoIndex]);
  const go = (index: number) => { const target = ref.current?.children[index] as HTMLElement | undefined; target?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest', inline: 'start' }); };
  return <section className="gallery" aria-label={label}><div className="gallery-track" ref={ref} tabIndex={0} onKeyDown={event => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); go(Math.max(0, Math.min(slides.length - 1, active + (event.key === 'ArrowRight' ? 1 : -1)))); } }} onScroll={() => { const el = ref.current; if (el) setActive(Math.round(el.scrollLeft / el.clientWidth)); }}>{slides.map((slide, i) => <div className="gallery-frame" key={slide.kind === 'image' ? `${slide.image.src}-${i}` : 'video'}>{slide.kind === 'image' ? <Media image={slide.image} priority={i === 0} sizes="(max-width: 700px) 100vw, 55vw" /> : <video ref={player} muted playsInline loop controls preload="none" poster={slide.video.poster.src} width={slide.video.width} height={slide.video.height} aria-label={slide.video.alt}><source src={slide.video.src} type={slide.video.type} /></video>}</div>)}</div><div className="gallery-thumbs">{slides.map((slide, i) => <button key={slide.kind === 'image' ? `${slide.image.src}-${i}` : 'video'} className={slide.kind === 'video' ? 'video-thumb' : undefined} onClick={() => go(i)} aria-label={slide.kind === 'video' ? watch : `${photo} ${i + 1}`} aria-pressed={active === i}><Media image={{ ...(slide.kind === 'image' ? slide.image : slide.video.poster), alt: '' }} sizes="80px" /><span aria-hidden="true">{slide.kind === 'video' ? '▶' : active === i ? '●' : '○'}</span></button>)}</div></section>;
}
