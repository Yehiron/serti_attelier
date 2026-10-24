import type { Metadata } from 'next';
import type { Alternates } from './api/types';
import { siteUrl } from './api/server';
import type { Locale } from './i18n';
export function pageMetadata(title: string, description: string, locale: Locale, alternates: Alternates, image?: string): Metadata {
  return { title, description, alternates: { canonical: alternates[locale], languages: alternates }, openGraph: { title, description, url: alternates[locale], locale: locale === 'es' ? 'es_CO' : 'en_US', ...(image ? { images: [new URL(image, siteUrl).href] } : {}) } };
}
export function PageAlternates({ alternates }: { alternates: Alternates }) { return <span hidden data-alternate-es={alternates.es} data-alternate-en={alternates.en} />; }
