import { locale } from 'next/root-params';
import { isLocale } from '@/lib/i18n';
import { NotFoundContent } from '@/components/not-found-content';
// A missing piece gets the jewelry wording ("found another home") instead of the generic page text.
export default async function NotFound() {
  const current = await locale();
  return <NotFoundContent locale={isLocale(current) ? current : 'es'} kind="piece" />;
}
