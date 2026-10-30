import type { Locale } from '@/lib/i18n';

/** Minimal decorative flag for the language switch: Colombia for Spanish, a simplified US flag (no stars) for English. */
export function Flag({ locale }: { locale: Locale }) {
  return locale === 'es'
    ? <svg className="flag" viewBox="0 0 3 2" aria-hidden="true"><rect width="3" height="1" fill="#fcd116" /><rect y="1" width="3" height=".5" fill="#003893" /><rect y="1.5" width="3" height=".5" fill="#ce1126" /></svg>
    : <svg className="flag" viewBox="0 0 19 10" aria-hidden="true"><rect width="19" height="10" fill="#b22234" />{[1, 3, 5].map(i => <rect key={i} y={(i * 10) / 7} width="19" height={10 / 7} fill="#fff" />)}<rect width="7.6" height={(4 * 10) / 7} fill="#3c3b6e" /></svg>;
}
