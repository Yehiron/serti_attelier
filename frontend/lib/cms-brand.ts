import type { CSSProperties } from 'react';
import type { Metadata } from 'next';
import type { Image } from './api/types';
export const brandColors = { wine: '#651c32', crimson: '#8a1538', cream: '#ead9cb', paper: '#dfc9b8', ink: '#330414', olive: '#7a7256', 'olive-deep': '#58513d' } as const;
export type BrandImage = { src: string; width: number; height: number };
export type BrandIdentity = Record<keyof typeof brandColors, string> & {
  title_font: 'ninna' | 'cormorant'; text_font: 'inter'; title_scale: number; text_scale: number;
  logo_light: BrandImage | null; logo_dark: BrandImage | null; monogram_light: BrandImage | null; monogram_dark: BrandImage | null; footer: BrandImage | null;
  icon: Record<string, string> | null; sharing: Image | null;
};
export const originalBrand: BrandIdentity = { ...brandColors, title_font: 'ninna', text_font: 'inter', title_scale: 100, text_scale: 100, logo_light: null, logo_dark: null, monogram_light: null, monogram_dark: null, footer: null, icon: null, sharing: null };
const hex = /^#[0-9a-fA-F]{6}$/;
/** Emit only deviations. Original identity keeps the exact historical style attribute. */
export function brandStyle(brand: BrandIdentity): CSSProperties {
  const style: Record<string, string | number> = { '--title-scale': [90,100,110,120].includes(brand.title_scale) ? brand.title_scale / 100 : 1, '--text-scale': [90,100,110,120].includes(brand.text_scale) ? brand.text_scale / 100 : 1 };
  for (const key of Object.keys(brandColors) as (keyof typeof brandColors)[]) {
    const value = brand[key];
    if (typeof value === 'string' && hex.test(value) && value.toLowerCase() !== brandColors[key]) style[`--color-${key}`] = value.toLowerCase();
  }
  if (brand.title_font === 'cormorant') style['--font-serif'] = 'var(--font-cormorant), "Cormorant Garamond", Georgia, serif';
  // CSS mask keeps the original mark: custom logos must never be recolored by a mask.
  return style as CSSProperties;
}
export function brandIcons(brand: BrandIdentity, defaults: Metadata['icons']): Metadata['icons'] {
  const icons = brand.icon;
  return icons ? { icon: [32,192,512].map(size => ({ url: icons[String(size)], sizes: `${size}x${size}`, type: 'image/png' })), shortcut: icons.ico, apple: icons['180'] } : defaults;
}
export function brandMetadata(brand: BrandIdentity, base: Metadata): Metadata {
  let result = base;
  if (brand.icon) result = { ...result, icons: brandIcons(brand, base.icons) };
  if (brand.sharing) result = { ...result, openGraph: { ...result.openGraph, images: [{ url: brand.sharing.src, width: brand.sharing.width, height: brand.sharing.height, alt: brand.sharing.alt }] }, twitter: { ...result.twitter, card: 'summary_large_image', images: [brand.sharing.src] } };
  return result;
}
export function brandLogoUrl(brand: BrandIdentity, siteUrl: string) {
  return new URL(brand.logo_light?.src || '/brand/logo/wordmark-wine.png', siteUrl).href;
}
