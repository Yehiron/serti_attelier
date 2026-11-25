import { Checkout } from '@/components/checkout';
import { locale } from 'next/root-params';
import { notFound } from 'next/navigation';
import { getDictionary } from '../dictionaries';
import { isLocale } from '@/lib/i18n';
import { getSettings } from '@/lib/api/server';
import { PageAlternates } from '@/lib/metadata';
import { href } from '@/lib/routes';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() {
  const dict = await getDictionary();
  return { title: dict.commerce.checkout, robots: { index: false, follow: true } };
}
export default async function Page() {
  const current = await locale(); if (!isLocale(current)) notFound();
  const [dict, settings] = await Promise.all([getDictionary(), getSettings(current)]);
  return <main id="main" className="commerce-page"><PageAlternates alternates={{ es: href('checkout', 'es'), en: href('checkout', 'en') }} /><header className="page-heading"><p className="eyebrow">SERTI · {dict.ui.unique}</p><h1>{dict.commerce.checkout}</h1></header><Checkout locale={current} dict={dict} settings={settings} /></main>;
}
