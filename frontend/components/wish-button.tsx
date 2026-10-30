'use client';
import { useState } from 'react';
import { useWishlist } from '@/lib/use-wishlist';
import { Heart } from './heart';
import type { Wish } from '@/lib/wishlist';
export function WishButton({ wish, save, remove }: { wish: Wish; save: string; remove: string }) {
  const { wishes, toggle } = useWishlist();
  const saved = wishes.some(x => x.sku === wish.sku);
  // Pulse only when the visitor saves it, not for pieces already saved on page load.
  const [pop, setPop] = useState(false);
  return <button type="button" className="wish-button" aria-label={saved ? remove : save} aria-pressed={saved} onClick={() => { setPop(!saved); toggle({ ...wish, addedAt: Date.now() }); }}><Heart filled={saved} pop={pop && saved} /></button>;
}
