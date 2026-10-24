import type { Image, Money } from './api/types.ts';
export type Wish = { sku: string; slugs: { es: string; en: string }; name: string; image: Image | null; price: Money; addedAt: number };
export const wishlistKey = 'serti_wishlist';
export type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;
export function parseWishlist(value: string | null): Wish[] {
  try {
    const data: unknown = JSON.parse(value ?? '[]');
    if (!Array.isArray(data)) return [];
    const seen = new Set<string>();
    return data.filter((x): x is Wish => {
      if (!x || typeof x !== 'object' || typeof x.sku !== 'string' || !x.sku || seen.has(x.sku) || typeof x.name !== 'string' || typeof x.slugs?.es !== 'string' || typeof x.slugs?.en !== 'string' || !Number.isFinite(x.price?.amount_cents) || x.price?.currency !== 'COP' || !Number.isFinite(x.addedAt)) return false;
      if (x.image !== null && (!x.image || typeof x.image.src !== 'string' || typeof x.image.srcset !== 'string' || typeof x.image.alt !== 'string' || !Number.isFinite(x.image.width) || !Number.isFinite(x.image.height))) return false;
      seen.add(x.sku); return true;
    }).slice(0, 200);
  } catch { return []; }
}
export function readWishlist(storage: StorageLike): Wish[] { try { return parseWishlist(storage.getItem(wishlistKey)); } catch { return []; } }
export function writeWishlist(storage: StorageLike, wishes: Wish[]) { try { storage.setItem(wishlistKey, JSON.stringify(wishes)); return true; } catch { return false; } }
export function toggleWish(wishes: Wish[], wish: Wish): Wish[] { return wishes.some(x => x.sku === wish.sku) ? wishes.filter(x => x.sku !== wish.sku) : [...wishes, wish].slice(-200); }
