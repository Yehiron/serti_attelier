'use client';
import { useSyncExternalStore } from 'react';
import type { WishStatus } from './api/types';
import { mergeWishlist, parseWishlist, toggleWish, wishlistKey, writeWishlist, type Wish } from './wishlist';
let memory = '[]';
let storageFailed = false;
const listeners = new Set<() => void>();
function snapshot() { if (storageFailed) return memory; try { return window.localStorage.getItem(wishlistKey) ?? memory; } catch { return memory; } }
function subscribe(callback: () => void) { listeners.add(callback); window.addEventListener('storage', callback); return () => { listeners.delete(callback); window.removeEventListener('storage', callback); }; }
export function useWishlist() {
  const value = useSyncExternalStore(subscribe, snapshot, () => '[]');
  const wishes = parseWishlist(value);
  function toggle(wish: Wish) {
    const next = toggleWish(parseWishlist(snapshot()), wish); memory = JSON.stringify(next);
    try { storageFailed = !writeWishlist(window.localStorage, next); } catch { storageFailed = true; }
    listeners.forEach(fn => fn());
  }
  function refresh(statuses: Record<string, WishStatus>) {
    const current = parseWishlist(snapshot());
    const next = mergeWishlist(current, statuses);
    const serialized = JSON.stringify(next);
    if (serialized === JSON.stringify(current)) return;
    memory = serialized;
    try { storageFailed = !writeWishlist(window.localStorage, next); } catch { storageFailed = true; }
    listeners.forEach(fn => fn());
  }
  return { wishes, toggle, refresh };
}
