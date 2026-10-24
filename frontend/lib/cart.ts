import { readResponse } from './api/problem.ts';
import type { Locale } from './i18n.ts';
import { emptyCart, mergeCart, type Cart } from './commerce.ts';
export async function browserRequest<T>(path: string, locale: Locale, options: RequestInit = {}): Promise<T> {
  const url = new URL(`/api/v1/${path}`, window.location.origin); url.searchParams.set('locale', locale);
  return readResponse<T>(await fetch(url.pathname + url.search, { ...options, credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } }));
}
export type CartSnapshot = { cart: Cart; loaded: boolean; error: boolean; drawer: boolean };
const initial: CartSnapshot = { cart: emptyCart, loaded: false, error: false, drawer: false };
let state = initial;
let queue: Promise<unknown> = Promise.resolve();
const listeners = new Set<() => void>();
const publish = (next: CartSnapshot) => { state = next; listeners.forEach(listener => listener()); };
export const cartSnapshot = () => state;
export const cartServerSnapshot = () => initial;
export function subscribeCart(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
// Serialize reads/mutations so an older read can never overwrite a successful mutation.
function operation(locale: Locale, path = 'cart', options?: RequestInit) {
  const run = queue.catch(() => {}).then(async () => {
    try { const cart = await browserRequest<Cart>(path, locale, options); publish({ ...state, cart: mergeCart(state.cart, cart), loaded: true, error: false }); return cart; }
    catch (error) { publish({ ...state, loaded: true, error: true }); throw error; }
  });
  queue = run; return run;
}
export const refreshCart = (locale: Locale) => operation(locale);
export const addToCart = (locale: Locale, sku: string) => operation(locale, 'cart/items', { method: 'POST', body: JSON.stringify({ sku }) });
export const removeFromCart = (locale: Locale, sku: string) => operation(locale, `cart/items/${encodeURIComponent(sku)}`, { method: 'DELETE' });
export const openCart = () => publish({ ...state, drawer: true });
export const closeCart = () => publish({ ...state, drawer: false });
export const dismissRemoved = () => publish({ ...state, cart: { ...state.cart, removed: [] } });
