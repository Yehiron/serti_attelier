import type { Locale } from '../i18n.ts';
export function formatCOP(cents: number, locale: Locale) {
  return new Intl.NumberFormat(locale === 'es' ? 'es-CO' : 'en-US', { style: 'currency', currency: 'COP', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(cents / 100);
}
export function whatsappUrl(number: string | null, message: string) {
  const digits = number?.replace(/\D/g, '');
  return digits ? `https://wa.me/${digits}?text=${encodeURIComponent(message)}` : null;
}
