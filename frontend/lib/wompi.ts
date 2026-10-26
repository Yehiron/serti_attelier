import type { WompiCheckout } from './api/types.ts';

const checkoutUrl = 'https://checkout.wompi.co/p/';
const required = ['public-key', 'currency', 'amount-in-cents', 'reference', 'signature:integrity', 'expiration-time'] as const;
const allowed = new Set<string>([...required, 'redirect-url', 'customer-data:email', 'customer-data:full-name', 'customer-data:phone-number', 'shipping-address:address-line-1', 'shipping-address:country', 'shipping-address:city', 'shipping-address:region', 'shipping-address:phone-number']);
export function wompiFormModel(checkout: WompiCheckout) {
  if (checkout.checkout_url !== checkoutUrl) throw new Error('Invalid checkout URL');
  const fields = Object.entries(checkout.fields).map(([name, value]) => {
    if (!allowed.has(name) || !['string', 'number', 'boolean'].includes(typeof value)) throw new Error('Invalid checkout field');
    const text = String(value);
    if (name === 'redirect-url' && !['https:', 'http:'].includes(new URL(text).protocol)) throw new Error('Invalid redirect URL');
    return { name, value: text };
  });
  if (required.some(name => !fields.some(field => field.name === name && field.value))) throw new Error('Missing checkout field');
  return { action: checkoutUrl, method: 'GET' as const, fields };
}
export function submitWompiCheckout(checkout: WompiCheckout) {
  const model = wompiFormModel(checkout);
  const form = document.createElement('form');
  form.method = model.method; form.action = model.action; form.hidden = true;
  for (const field of model.fields) {
    const input = document.createElement('input'); input.type = 'hidden'; input.name = field.name; input.value = field.value; form.appendChild(input);
  }
  document.body.appendChild(form);
  // Keep the form connected until the browser completes its queued navigation.
  try { HTMLFormElement.prototype.submit.call(form); } catch (error) { form.remove(); throw error; }
}
export function withoutTransactionId(value: string) {
  const url = new URL(value); url.searchParams.delete('id'); return url.pathname + url.search + url.hash;
}
