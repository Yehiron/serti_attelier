'use client';
import { useEffect, useSyncExternalStore } from 'react';
import type { Locale } from './i18n';
import { cartSnapshot, cartServerSnapshot, subscribeCart, refreshCart } from './cart';
let mounts = 0;
let focusRefresh: (() => void) | null = null;
export function useCart(locale: Locale) {
  const state = useSyncExternalStore(subscribeCart, cartSnapshot, cartServerSnapshot);
  useEffect(() => {
    if (mounts++ === 0) {
      focusRefresh = () => { void refreshCart(locale).catch(() => {}); };
      focusRefresh(); window.addEventListener('focus', focusRefresh);
    }
    return () => {
      if (--mounts === 0 && focusRefresh) { window.removeEventListener('focus', focusRefresh); focusRefresh = null; }
    };
  }, [locale]);
  return state;
}
