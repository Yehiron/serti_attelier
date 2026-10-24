/* eslint-disable @next/next/no-img-element -- API supplies responsive image renditions. */
import type { Image as ApiImage } from '@/lib/api/types';
export function Media({ image, className = '', priority = false, sizes = '(max-width: 700px) 100vw, 50vw' }: { image: ApiImage; className?: string; priority?: boolean; sizes?: string }) {
  return <img className={className} src={image.src} srcSet={image.srcset || undefined} sizes={sizes} width={image.width || 960} height={image.height || 1200} alt={image.alt} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : undefined} />;
}
export function Ornament() { return <img className="ornament" src="/brand/ornament.webp" width="502" height="353" alt="" loading="lazy" />; }
export function Monogram() { return <img className="monogram" src="/brand/monogram.webp" width="512" height="512" alt="SERTI" />; }
export function Leather() { return <div className="leather"><img src="/brand/brand-leather.webp" width="1284" height="2778" alt="" loading="lazy" /></div>; }
