import type { Image, Money, Problem, SaleState, WompiCheckout, PaymentDetails } from './api/types.ts';
import type { Locale } from './i18n.ts';
export type CartItem = { sku: string; slug: string; name: string; image: Image | null; price: Money; sale_price: Money | null; effective_price: Money; sale_state: SaleState; purchasable: boolean };
export type Cart = { items: CartItem[]; removed: { sku: string; name: string; reason: 'sold' | 'preorder' | 'unavailable' }[]; count: number; subtotal: Money };
export type Quote = { items: { sku: string; name: string; unit_price_cents: number; discount_cents: number }[]; subtotal_cents: number; discount_cents: number; shipping_cents: number; certificate_cents: number; total_cents: number; currency: 'COP'; coupon: { code: string; applied: boolean; reason: string | null } | null; payment_channels: ('wompi' | 'manual')[] };
export type CreatedOrder = { wompi: WompiCheckout | null; number: string; public_token: string; payment_channel: 'wompi' | 'manual'; payment_status: string; total_cents: number; reservation_expires_at: string | null; manual_instructions: string | null };
export type Order = Omit<CreatedOrder, 'public_token'> & PaymentDetails & Omit<Quote, 'items' | 'coupon' | 'payment_channels'> & { created_at: string; locale: Locale; fulfillment_status: string; fulfillment: import('./api/types.ts').Fulfillment; payment_review: boolean; items: { sku: string; name: string; image: Image | null; unit_price_cents: number; discount_cents: number; piece_number: string | null }[]; wants_certificate: boolean; shipping: { department: string; municipality: string } };
export const emptyCart: Cart = { items: [], removed: [], count: 0, subtotal: { amount_cents: 0, currency: 'COP' } };
// Reconcile authoritative server items; keep removal notices until the shopper dismisses them.
export function mergeCart(previous: Cart, incoming: Cart): Cart {
  const items = [...new Map(incoming.items.map(item => [item.sku, item])).values()];
  const present = new Set(items.map(item => item.sku));
  return { ...incoming, items, count: items.length, removed: [...new Map([...previous.removed, ...incoming.removed].filter(item => !present.has(item.sku)).map(item => [item.sku, item])).values()] };
}
export const couponKeys = { coupon_invalid: 'couponInvalid', coupon_expired: 'couponExpired', coupon_exhausted: 'couponExhausted', coupon_not_applicable: 'couponNotApplicable', coupon_min_subtotal: 'couponMinSubtotal' } as const;
export function couponMessageKey(reason: string) { return couponKeys[reason as keyof typeof couponKeys] ?? 'couponInvalid'; }
export function fieldErrors(problem: Problem): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const [key, value] of Object.entries(problem.errors ?? {})) {
    if (Array.isArray(value)) result[key] = value;
    else for (const [field, messages] of Object.entries(value)) result[`${key}.${field}`] = messages;
  }
  for (const [source, target] of [['accepted_terms_version', 'terms'], ['accepted_privacy_version', 'privacy']] as const) {
    if (result[source]) { result[target] = result[source]; delete result[source]; }
  }
  return result;
}
export function normalizePhone(value: string) { const digits = value.replace(/\D/g, ''); return `+${digits.length === 10 ? '57' : ''}${digits}`; }
export function checkoutPayload(data: FormData, choices: { coupon: string; certificate: boolean; channel: 'wompi' | 'manual'; terms: number | null; privacy: number | null; locale: Locale }) {
  const value = (key: string) => String(data.get(key) ?? '').trim();
  return { contact: { name: value('contact.name'), email: value('contact.email').toLowerCase(), phone: normalizePhone(value('contact.phone')) }, shipping: { municipality_code: value('shipping.municipality_code'), address_line: value('shipping.address_line'), address_extra: value('shipping.address_extra'), notes: value('shipping.notes') }, coupon_code: choices.coupon.trim(), wants_certificate: choices.certificate, payment_channel: choices.channel, accepted_terms_version: data.get('terms') === 'on' ? choices.terms : null, accepted_privacy_version: data.get('privacy') === 'on' ? choices.privacy : null, locale: choices.locale };
}
export type CheckoutPayload = ReturnType<typeof checkoutPayload>;
export type AttemptStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export const attemptStorageKey = 'serti_checkout_attempt';
export type Attempt = { key: string; body: CheckoutPayload; order?: string };
export function readAttempt(storage: AttemptStorage): Attempt | null {
  const raw = storage.getItem(attemptStorageKey); if (!raw) return null;
  try { const attempt = JSON.parse(raw); return typeof attempt.key === 'string' && attempt.body?.contact && attempt.body?.shipping ? attempt : null; } catch { return null; }
}
// Persist the exact body as well as the key: retries after a refresh cannot change a pending order.
export function checkoutAttempt(storage: AttemptStorage, body: CheckoutPayload, uuid: () => string): Attempt {
  const existing = readAttempt(storage); if (existing) return existing;
  const attempt = { key: uuid(), body }; storage.setItem(attemptStorageKey, JSON.stringify(attempt)); return attempt;
}
export function clearAttempt(storage: AttemptStorage) { storage.removeItem(attemptStorageKey); }
// Once the API answered, the order exists: keep its token so a later visit links to it
// instead of replaying the request, and so the order page can retire the attempt.
export function rememberAttemptOrder(storage: AttemptStorage, token: string) {
  const attempt = readAttempt(storage); if (attempt) storage.setItem(attemptStorageKey, JSON.stringify({ ...attempt, order: token }));
}
export function clearAttemptForOrder(storage: AttemptStorage, token: string) {
  if (readAttempt(storage)?.order === token) clearAttempt(storage);
}
export function formatDeadline(value: string, locale: Locale) { return new Intl.DateTimeFormat(locale === 'es' ? 'es-CO' : 'en-US', { timeZone: 'America/Bogota', dateStyle: 'long', timeStyle: 'short' }).format(new Date(value)); }

// One persisted key per order and failed reference: uncertain retries replay the same request.
export function paymentAttemptKey(storage: AttemptStorage, token: string, reference: string, uuid: () => string) {
  const name = `serti_payment_attempt:${token}`;
  const raw = storage.getItem(name);
  if (raw) {
    try { const saved = JSON.parse(raw); if (saved.reference === reference && typeof saved.key === 'string') return saved.key as string; } catch { /* Replace malformed storage. */ }
  }
  const key = uuid(); storage.setItem(name, JSON.stringify({ reference, key })); return key;
}
export function clearPaymentAttempt(storage: AttemptStorage, token: string) { storage.removeItem(`serti_payment_attempt:${token}`); }
