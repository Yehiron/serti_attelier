import type { Locale } from './i18n.ts';
import { href } from './routes.ts';
import type { Named } from './api/types.ts';

export function pieceEyebrow(unique: string, number: string | null | undefined) {
  return [unique, number?.trim()].filter(Boolean).join(' · ');
}
export function stoneColor(name: string) {
  const value = name.toLocaleLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  if (/esmerald|emerald/.test(value)) return '#1f7a55';
  if (/rubi|ruby/.test(value)) return '#a51d38';
  if (/zafiro|sapphire/.test(value)) return '#315d9b';
  if (/diamante|diamond/.test(value)) return '#eef1f3';
  return '#c9a96e';
}
export function collectionLink(locale: Locale, collections: Named[], category: Named | null) {
  return collections[0] ? href('collection', locale, collections[0].slug) : category ? href('category', locale, category.slug) : href('catalog', locale);
}
