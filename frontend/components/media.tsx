import type { BrandIdentity } from '@/lib/cms-brand';
import { focalPosition } from '@/lib/cms-focal';
/* eslint-disable @next/next/no-img-element -- API supplies responsive image renditions. */
import type { Image as ApiImage } from '@/lib/api/types';
export function Media({ image, className = '', priority = false, sizes = '(max-width: 700px) 100vw, 50vw' }: { image: ApiImage; className?: string; priority?: boolean; sizes?: string }) {
  return <img className={className} style={{ objectPosition: focalPosition(image) }} src={image.src} srcSet={image.srcset || undefined} sizes={sizes} width={image.width || 960} height={image.height || 1200} alt={image.alt} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : undefined} />;
}
/* Official logo files (docs/marca.md). Wine is for light backgrounds and gold for wine/dark
   ones: both are rendered and CSS shows the one that fits; a hidden lazy image is never fetched. */
type Tone = 'wine' | 'gold';
const tones: Tone[] = ['wine', 'gold'];
export function Ornament() {
  return <span className="ornament">{tones.map(tone => <img key={tone} className={`tone-${tone}`} src={`/brand/logo/ornament-${tone}.webp`} width="560" height="209" alt="" loading="lazy" />)}</span>;
}
/** The full wordmark stays visible on desktop and mobile. */
export function BrandLogo({ brand }: { brand?: BrandIdentity }) {
  return <span className="brand-logo">{tones.map(tone => <picture key={tone} className={`tone-${tone}`}>{(tone === 'wine' ? brand?.monogram_light : brand?.monogram_dark)?.src && <source media="(max-width: 700px)" srcSet={(tone === 'wine' ? brand?.monogram_light : brand?.monogram_dark)?.src} />}<img src={(tone === 'wine' ? brand?.logo_light : brand?.logo_dark)?.src || `/brand/logo/wordmark-${tone}.webp`} width="320" height="103" alt="SERTI Jewelry Atelier" loading="lazy" /></picture>)}</span>;
}
/** Menu dialog logo: lazy, so it is fetched only when the menu opens. */
export function Wordmark({ brand }: { brand?: BrandIdentity }) { return <img className="wordmark" src={brand?.logo_dark?.src || "/brand/logo/wordmark-gold.webp"} width="320" height="103" alt="SERTI Jewelry Atelier" loading="lazy" />; }
export function Signature({ brand }: { brand?: BrandIdentity }) { return <img className="signature" src={brand?.footer?.src || "/brand/logo/monogram-tagline-gold.webp"} width="300" height="264" alt="SERTI · Timeless and Sophisticated" loading="lazy" />; }
export function Leather() { return <div className="leather"><img src="/brand/brand-leather.webp" width="1284" height="2778" alt="" loading="lazy" /></div>; }
