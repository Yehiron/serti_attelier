import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import type { Quote } from '@/lib/commerce';
import { formatCOP } from '@/lib/api/format';
export function Totals({ data, locale, dict }: { data: Pick<Quote, 'subtotal_cents' | 'discount_cents' | 'shipping_cents' | 'certificate_cents' | 'total_cents'>; locale: Locale; dict: Dictionary }) {
  return <dl className="commerce-totals">{(['subtotal', 'discount', 'shipping', 'certificate', 'total'] as const).map(key => <div key={key}><dt>{dict.commerce[key]}</dt><dd>{key === 'discount' && data.discount_cents > 0 ? '−' : ''}{formatCOP(data[`${key}_cents`], locale)}</dd></div>)}</dl>;
}
