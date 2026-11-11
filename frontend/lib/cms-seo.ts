import type { Metadata } from 'next';
import type { CmsSeo } from './api/types.ts';

/** Empty editorial settings must preserve the previous metadata byte for byte. */
export function applyCmsSeo(base: Metadata, seo: CmsSeo | undefined, siteUrl: string, draft = false): Metadata {
  if (!seo || !(seo.title || seo.description || seo.image || seo.noindex)) return base;
  const title = seo.title || base.title;
  const description = seo.description || base.description;
  const image = seo.image ? new URL(seo.image.src, siteUrl).href : undefined;
  return {
    ...base, title, description,
    openGraph: { ...base.openGraph, ...(seo.title ? { title: seo.title } : {}), ...(seo.description ? { description: seo.description } : {}), ...(image ? { images: [image] } : {}) },
    twitter: { ...base.twitter, card: image || (base.twitter && 'images' in base.twitter && base.twitter.images) ? 'summary_large_image' : 'summary', ...(typeof title === 'string' ? { title } : {}), ...(description ? { description } : {}), ...(image ? { images: [image] } : {}) },
    ...(draft ? { robots: { index: false, follow: false } } : seo.noindex ? { robots: { index: false, follow: true } } : {}),
  };
}
