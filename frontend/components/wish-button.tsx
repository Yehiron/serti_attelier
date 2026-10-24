'use client';
import { useWishlist } from '@/lib/use-wishlist';
import type { Wish } from '@/lib/wishlist';
export function WishButton({ wish, save, remove }: { wish: Wish; save: string; remove: string }) {
  const { wishes, toggle } = useWishlist();
  const saved = wishes.some(x => x.sku === wish.sku);
  return <button type="button" className="wish-button" aria-label={saved ? remove : save} aria-pressed={saved} onClick={() => toggle({ ...wish, addedAt: Date.now() })}><span aria-hidden="true">{saved ? '♥' : '♡'}</span></button>;
}
