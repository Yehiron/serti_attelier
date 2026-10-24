import Link from 'next/link';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import type { Locale } from '@/lib/i18n';
import { href } from '@/lib/routes';
export function CustomPieceLink({ locale, dict, whatsapp }: { locale: Locale; dict: Dictionary; whatsapp?: string | null }) {
  return whatsapp ? <a className="text-link" href={whatsapp} target="_blank" rel="noopener noreferrer">{dict.commerce.bespoke} ↗</a> : <Link className="text-link" href={href('personalize', locale)}>{dict.commerce.bespoke} ↗</Link>;
}
