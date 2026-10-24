import type { Locale } from './i18n.ts';

export const routes = {
  home: ['', ''], catalog: ['joyeria', 'jewelry'], category: ['joyeria', 'jewelry'],
  stone: ['piedras', 'stones'], collection: ['colecciones', 'collections'],
  piece: ['piezas', 'pieces'], personalize: ['personaliza', 'customize'],
  story: ['historia', 'story'], contact: ['contacto', 'contact'],
  wishlist: ['deseos', 'wishlist'], search: ['buscar', 'search'], legal: ['legal', 'legal'],
} as const;
export type RouteKey = keyof typeof routes;
export function href(key: RouteKey, locale: Locale, slug?: string) {
  const segment = routes[key][locale === 'es' ? 0 : 1];
  return `/${locale}${segment ? `/${segment}` : ''}${slug ? `/${encodeURIComponent(slug)}` : ''}`;
}
export function routeDecision(pathname: string): { kind: 'next' | 'rewrite' | 'redirect'; pathname: string } {
  const [, language, segment, ...tail] = pathname.split('/');
  if (language !== 'es' && language !== 'en') return { kind: 'next', pathname };
  const index = language === 'es' ? 0 : 1;
  const pair = Object.values(routes).find(p => segment && p.includes(segment as never));
  if (!pair) return { kind: 'next', pathname };
  const suffix = tail.length ? `/${tail.join('/')}` : '';
  const canonical = `/${language}/${pair[index]}${suffix}`;
  if (segment !== pair[index]) return { kind: 'redirect', pathname: canonical };
  if (language === 'en' && pair[0] !== pair[1]) return { kind: 'rewrite', pathname: `/en/${pair[0]}${suffix}` };
  return { kind: 'next', pathname };
}
export function safePreviewPath(path: string | null) {
  if (!path || !/^\/(es|en)(\/|$)/.test(path) || /[\\\r\n]/.test(path)) return '/es';
  try { const url = new URL(path, 'https://serti.localhost'); return url.origin === 'https://serti.localhost' && /^\/(es|en)(\/|$)/.test(url.pathname) ? url.pathname + url.search : '/es'; } catch { return '/es'; }
}
