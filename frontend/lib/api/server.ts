import 'server-only';
import { cacheLife, cacheTag } from 'next/cache';
import { cookies, draftMode } from 'next/headers';
import { connection } from 'next/server';
import { cache } from 'react';
import type { Locale } from '../i18n';
import { readResponse, ApiError } from './problem';
import type { Catalog, CmsPage, Home, Personalization, PieceDetail, Settings, Taxonomy } from './types';
export { ApiError };
export const siteUrl = process.env.PUBLIC_SITE_URL ?? 'https://serti.localhost';
export async function request<T>(path: string, locale: Locale, query = '', preview?: string): Promise<T> {
  const params = new URLSearchParams(query); params.set('locale', locale);
  if (preview) params.set('preview', preview);
  // Internal calls skip Caddy: declare the scheme so Django's HTTPS redirect does not apply.
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Forwarded-Proto': 'https' };
  if (process.env.INTERNAL_API_TOKEN) headers['X-Internal-Token'] = process.env.INTERNAL_API_TOKEN;
  try {
    const response = await fetch(`${(process.env.API_INTERNAL_URL ?? 'http://backend:8000/api/v1').replace(/\/$/, '')}/${path}?${params}`, { headers, cache: 'no-store', signal: AbortSignal.timeout(8000) });
    return await readResponse<T>(response);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(503, { code: 'network_unavailable' });
  }
}
type CachedResult<T> = { ok: true; data: T } | { ok: false; status: number; problem: import('./types').Problem };
async function cachedResult<T>(path: string, locale: Locale, query: string, tag: string): Promise<CachedResult<T>> {
  'use cache';
  cacheLife({ stale: 60, revalidate: 60, expire: 300 });
  cacheTag(tag, path.startsWith('catalog/') ? 'catalog' : 'cms');
  try {
    return { ok: true, data: await request<T>(path, locale, query) };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    // Keep errors serializable across the cache boundary and retry them quickly.
    cacheLife({ stale: 30, revalidate: 1, expire: 5 });
    return { ok: false, status: error.status, problem: error.problem };
  }
}
async function cachedRead<T>(path: string, locale: Locale, query: string, tag: string): Promise<T> {
  // The API is not reachable while building (docker build, CI): stop prerendering here so
  // data is fetched at request time. Results are still cached in memory across requests.
  await connection();
  const result = await cachedResult<T>(path, locale, query, tag);
  if (!result.ok) throw new ApiError(result.status, result.problem);
  return result.data;
}
export async function getCopyrightYear() {
  'use cache';
  cacheLife('days');
  return new Date().getFullYear();
}
export const previewToken = cache(async () => {
  if (!(await draftMode()).isEnabled) return undefined;
  const token = (await cookies()).get('serti_preview')?.value;
  if (!token) throw new ApiError(403, { code: 'preview_invalid' });
  return token;
});
async function cmsRead<T>(path: string, locale: Locale) {
  const token = await previewToken();
  return token ? request<T>(path, locale, '', token) : cachedRead<T>(path, locale, '', 'cms');
}
export const getHome = (locale: Locale) => cmsRead<Home>('cms/home', locale);
// Published reads for sitemap generation never touch request cookies.
export const getPublishedPage = (locale: Locale, slug: string) => cachedRead<CmsPage>(`cms/pages/${encodeURIComponent(slug)}`, locale, '', 'cms');
export const getPage = (locale: Locale, slug: string, byKind = false) => cmsRead<CmsPage>(`cms/pages/${byKind ? 'kind/' : ''}${encodeURIComponent(slug)}`, locale);
export const getTaxonomy = (locale: Locale) => cachedRead<Taxonomy>('catalog/taxonomy', locale, '', 'catalog');
export const getCatalog = (locale: Locale, query = '') => cachedRead<Catalog>('catalog/pieces', locale, query, 'catalog');
export const getPiece = (locale: Locale, slug: string) => cachedRead<PieceDetail>(`catalog/pieces/${encodeURIComponent(slug)}`, locale, '', `piece:${slug}`);
export const getSettings = (locale: Locale) => cachedRead<Settings>('site/settings', locale, '', 'cms');
export const getPersonalization = (locale: Locale) => cachedRead<Personalization>('cms/personalization', locale, '', 'cms');
export const emptyTaxonomy: Taxonomy = { categories: [], collections: [], stones: [], materials: [] };
export const emptySettings: Settings = { title_scale: 1, text_scale: 1, whatsapp: { number: null, general_url: null }, social: [], support_email: null, legal_pages: [] };
export async function optionalPage(locale: Locale, kind: string) {
  try { return await getPage(locale, kind, true); } catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
}

// Customer order data must never enter a shared cache, including during builds.
export async function getOrder(locale: Locale, token: string) {
  await connection();
  return request<import('../commerce').Order>(`orders/${encodeURIComponent(token)}`, locale);
}
