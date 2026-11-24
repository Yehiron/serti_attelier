import type { WompiCheckout } from './api/types.ts';

const checkoutUrl = 'https://checkout.wompi.co/p/';
const required = ['public-key', 'currency', 'amount-in-cents', 'reference', 'signature:integrity', 'expiration-time'] as const;
const allowed = new Set<string>([...required, 'redirect-url', 'customer-data:email', 'customer-data:full-name', 'customer-data:phone-number', 'customer-data:phone-number-prefix', 'shipping-address:address-line-1', 'shipping-address:country', 'shipping-address:city', 'shipping-address:region', 'shipping-address:phone-number']);
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

type WidgetResult = { transaction?: { id?: string } };
type WidgetConfiguration = {
  currency: string; amountInCents: number; reference: string; publicKey: string;
  signature: { integrity: string }; redirectUrl?: string; expirationTime: string;
  customerData?: Record<string, string>; shippingAddress?: Record<string, string>;
};
declare global { interface Window { WidgetCheckout?: new (config: WidgetConfiguration) => { open: (callback: (result: WidgetResult) => void) => void } } }
export function widgetConfig(checkout: WompiCheckout): WidgetConfiguration {
  const fields = Object.fromEntries(wompiFormModel(checkout).fields.map(({ name, value }) => [name, value]));
  const amount = Number(fields['amount-in-cents']);
  if (!/^\d+$/.test(fields['amount-in-cents']) || !Number.isSafeInteger(amount) || amount <= 0) throw new Error('Invalid amount');
  const group = (prefix: string, names: Record<string, string>) => Object.fromEntries(Object.entries(names).filter(([key]) => fields[`${prefix}:${key}`] !== undefined).map(([key, value]) => [value, fields[`${prefix}:${key}`]]));
  const customerData = group('customer-data', { email: 'email', 'full-name': 'fullName', 'phone-number': 'phoneNumber', 'phone-number-prefix': 'phoneNumberPrefix' });
  const shippingAddress = group('shipping-address', { 'address-line-1': 'addressLine1', country: 'country', city: 'city', region: 'region', 'phone-number': 'phoneNumber' });
  return { currency: fields.currency, amountInCents: amount, reference: fields.reference, publicKey: fields['public-key'], signature: { integrity: fields['signature:integrity'] }, expirationTime: fields['expiration-time'], ...(fields['redirect-url'] ? { redirectUrl: fields['redirect-url'] } : {}), ...(Object.keys(customerData).length ? { customerData } : {}), ...(Object.keys(shippingAddress).length ? { shippingAddress } : {}) };
}
let widgetScript: Promise<void> | undefined;
function loadWidget() {
  if (window.WidgetCheckout) return Promise.resolve();
  if (!widgetScript) widgetScript = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script'); script.src = 'https://checkout.wompi.co/widget.js'; script.async = true;
    const timer = window.setTimeout(() => { script.remove(); reject(new Error('Widget timeout')); }, 8000);
    script.onload = () => { window.clearTimeout(timer); resolve(); };
    script.onerror = () => { window.clearTimeout(timer); script.remove(); reject(new Error('Widget unavailable')); };
    document.head.appendChild(script);
  }).catch(error => { widgetScript = undefined; throw error; });
  return widgetScript;
}
// Wompi does not call back when its window is closed without paying: it keeps the
// `.waybox-modal` node and adds `waybox-modal-final-close` (observed in sandbox, 2026-11).
export function watchWidgetClose(onClose: () => void, root: ParentNode & Node = document.body) {
  let seen = false; let done = false;
  const check = () => {
    if (done) return;
    const modal = root.querySelector('.waybox-modal:not(.waybox-modal-final-close)');
    if (modal) { seen = true; return; }
    if (seen) { done = true; observer.disconnect(); onClose(); }
  };
  const observer = new MutationObserver(check);
  observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  check();
  return () => { done = true; observer.disconnect(); };
}
export async function openWompiWidget(checkout: WompiCheckout, onResult: (result: WidgetResult) => void, onClose?: () => void) {
  const config = widgetConfig(checkout);
  try {
    await loadWidget();
    if (!window.WidgetCheckout) throw new Error('Widget unavailable');
    const stop = onClose ? watchWidgetClose(onClose) : undefined;
    try { new window.WidgetCheckout(config).open(onResult); } catch (error) { stop?.(); throw error; }
  } catch { submitWompiCheckout(checkout); }
}
