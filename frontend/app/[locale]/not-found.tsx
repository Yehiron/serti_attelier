import { locale } from 'next/root-params';
import { isLocale } from '@/lib/i18n';
import { NotFoundContent } from '@/components/not-found-content';
export default async function NotFound() {
  const current = await locale();
  return <NotFoundContent locale={isLocale(current) ? current : 'es'} />;
}
