import { locale } from 'next/root-params';
import { notFound } from 'next/navigation';
import { getDictionary } from '../dictionaries';
import { isLocale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { getSettings } from '@/lib/api/server';
import { PageAlternates, pageMetadata } from '@/lib/metadata';
import { WishlistPage } from '@/components/wishlist-page';

// Catalog/CMS data is read from the API at request time (it is unreachable at build
// time), so navigations into this segment are allowed to wait for it.
export const instant = false;
export async function generateMetadata() { const current = await locale(); if (!isLocale(current)) notFound(); const dict = await getDictionary(); return { ...pageMetadata(dict.nav.wishlist, dict.ui.wishlistHelp, current, { es: href('wishlist','es'), en: href('wishlist','en') }), robots: { index: false, follow: true } }; }
export default async function Page() { const current = await locale(); if (!isLocale(current)) notFound(); const [dict, settings] = await Promise.all([getDictionary(), getSettings(current)]); return <main id="main" className="utility-page"><PageAlternates alternates={{ es: href('wishlist', 'es'), en: href('wishlist', 'en') }} /><header className="page-heading"><p className="eyebrow">SERTI</p><h1>{dict.nav.wishlist}</h1></header><WishlistPage locale={current} dict={dict} number={settings.whatsapp.number} /></main>; }
