import 'server-only';
import { decodeOrderProbe, orderProbeHeader } from '../order-probe';
import { cacheLife, cacheTag } from 'next/cache';
import { cookies, draftMode, headers as requestHeaders } from 'next/headers';
import { connection } from 'next/server';
import { cache } from 'react';
import type { Locale } from '../i18n';
import { readResponse, ApiError } from './problem';
import type { Catalog, CmsMenu, CmsPage, Home, Personalization, PieceDetail, Settings, Taxonomy } from './types';
export { ApiError };
export const siteUrl = process.env.PUBLIC_SITE_URL ?? 'https://serti.localhost';
export async function request<T>(path: string, locale: Locale, query = '', preview?: string, orderIp?: string): Promise<T> {
  const params = new URLSearchParams(query); params.set('locale', locale);
  if (preview) params.set('preview', preview);
  // Internal calls skip Caddy: declare the scheme so Django's HTTPS redirect does not apply.
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Forwarded-Proto': 'https' };
  if (process.env.INTERNAL_API_TOKEN) headers['X-Internal-Token'] = process.env.INTERNAL_API_TOKEN;
  if (orderIp) headers['X-Forwarded-For'] = orderIp;
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
  cacheLife(path.startsWith('catalog/') ? { stale: 60, revalidate: 60, expire: 300 } : { stale: 0, revalidate: 3600, expire: 14400 });
  cacheTag(tag, path.startsWith('catalog/') ? 'catalog' : 'cms');
  try {
    const data = await request<T>(path, locale, query);
    // Slug reads acquire the stable document tag after resolving the published page.
    if (path.startsWith('cms/pages/') && data && typeof data === 'object' && 'kind' in data && typeof data.kind === 'string') cacheTag(`cms:page:${data.kind}`);
    return { ok: true, data };
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
  // `next dev` serves a stale "use cache" entry once after revalidateTag (by design, see
  // next/dist/server/lib/cache-handlers/default.js), so a publish would look delayed there.
  // Development reads CMS content live; production keeps tag invalidation (docs/cms-fase-8.md).
  if (process.env.NODE_ENV === 'development' && tag.startsWith('cms')) return request<T>(path, locale, query);
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
export function cmsTag(path: string): string {
  if (path.startsWith('cms/pages/kind/')) return `cms:page:${path.split('/').at(-1)}`;
  // Slug misses also need invalidation when an address is published for the first time.
  if (path.startsWith('cms/pages/')) return 'cms:pages';
  return path.replace('cms/menus/', 'cms:menu:').replace('cms/', 'cms:').replace('site/settings', 'cms:settings');
}
async function cmsRead<T>(path: string, locale: Locale) {
  const token = await previewToken();
  if (token) return request<T>(path, locale, '', token);
  return cachedRead<T>(path, locale, '', cmsTag(path));
}
export const getBrand = cache((locale: Locale) => cmsRead<import('../cms-brand').BrandIdentity>('cms/brand', locale));
export const getMenu = cache((locale: Locale, menu: 'main' | 'footer') => cmsRead<CmsMenu>(`cms/menus/${menu}`, locale));
export const getPublishedPageByKind = (locale: Locale, kind: string) => cachedRead<CmsPage>(`cms/pages/kind/${kind}`, locale, '', `cms:page:${kind}`);
export const getHome = cache((locale: Locale) => cmsRead<Home>('cms/home', locale));
// Published reads for sitemap generation never touch request cookies.
export const getPublishedPage = (locale: Locale, slug: string) => cachedRead<CmsPage>(`cms/pages/${encodeURIComponent(slug)}`, locale, '', 'cms:pages');
export const getPage = cache((locale: Locale, slug: string, byKind = false) => cmsRead<CmsPage>(`cms/pages/${byKind ? 'kind/' : ''}${encodeURIComponent(slug)}`, locale));
// Deduplicate within a render, without retaining an outdated menu across requests.
export const getTaxonomy = cache(async (locale: Locale) => {
  await connection();
  return request<Taxonomy>('catalog/taxonomy', locale);
});
export const getCatalog = (locale: Locale, query = '') => cachedRead<Catalog>('catalog/pieces', locale, query, 'catalog');
export const getPiece = (locale: Locale, slug: string) => cachedRead<PieceDetail>(`catalog/pieces/${encodeURIComponent(slug)}`, locale, '', `piece:${slug}`);
export const getSettings = (locale: Locale) => cachedRead<Settings>('site/settings', locale, '', 'cms:settings');
export const getPersonalization = (locale: Locale) => cachedRead<Personalization>('cms/personalization', locale, '', 'cms:personalization');
export const emptyTaxonomy: Taxonomy = { categories: [], collections: [], stones: [], materials: [] };
export const emptySettings: Settings = { title_scale: 1, text_scale: 1, whatsapp: { number: null, general_url: null }, social: [], support_email: null, legal_pages: [] };
export async function optionalPage(locale: Locale, kind: string) {
  try { return await getPage(locale, kind, true); } catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
}

// Customer order data must never enter a shared cache, including during builds.
export async function getOrder(locale: Locale, token: string) {
  await connection();
  const incoming = await requestHeaders();
  const probe = decodeOrderProbe(incoming.get(orderProbeHeader), token, locale);
  if (probe) {
    if (probe.status < 200 || probe.status >= 300) throw new ApiError(probe.status, probe.body as import('./types').Problem);
    return probe.body as import('../commerce').Order;
  }
  const ip = incoming.get('x-forwarded-for')?.split(',').at(-1)?.trim();
  return request<import('../commerce').Order>(`orders/${encodeURIComponent(token)}`, locale, '', undefined, ip);
}
