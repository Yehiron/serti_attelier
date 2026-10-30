import Link from 'next/link';
import { draftMode } from 'next/headers';
import type { Dictionary } from '@/app/[locale]/dictionaries';
import { getSettings, getTaxonomy, emptySettings, emptyTaxonomy, siteUrl, getCopyrightYear } from '@/lib/api/server';
import type { Locale } from '@/lib/i18n';
import { href } from '@/lib/routes';
import { Navigation } from './navigation';
import { Signature } from './media';
import { FloatingWhatsApp } from './whatsapp';
export async function Header({ locale, dict }: { locale: Locale; dict: Dictionary }) {
  const [taxonomy, settings] = await Promise.all([getTaxonomy(locale).catch(() => emptyTaxonomy), getSettings(locale).catch(() => emptySettings)]);
  return <Navigation locale={locale} dict={dict} taxonomy={taxonomy} whatsapp={settings.whatsapp.general_url} />;
}
export async function Footer({ locale, dict }: { locale: Locale; dict: Dictionary }) {
  const settings = await getSettings(locale).catch(() => emptySettings);
  const year = await getCopyrightYear();
  const organization = { '@context': 'https://schema.org', '@type': 'Organization', name: 'SERTI', url: siteUrl, logo: new URL('/brand/logo/wordmark-wine.png', siteUrl).href, sameAs: settings.social.map(x => x.url), ...(settings.support_email ? { email: settings.support_email } : {}) };
  return <><script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(organization).replace(/</g, '\\u003c') }} /><footer className="site-footer"><p className="eyebrow">SERTI · Colombia</p><h2>{dict.ui.brand}</h2><Link className="text-link" href={href('personalize', locale)}>{dict.nav.personalize} ↗</Link><div className="footer-content"><Signature /><p>{dict.home.lede}<br />{dict.ui.shipping}</p><nav aria-label={dict.ui.legal}>{settings.legal_pages.map(x => <Link key={x.kind} href={x.href}>{x.title}</Link>)}</nav><div>{settings.support_email && <a href={`mailto:${settings.support_email}`}>{settings.support_email}</a>}{settings.social.map(x => <a key={x.network} href={x.url} rel="noopener noreferrer" target="_blank">{x.network} ↗</a>)}</div></div><div className="footer-bottom"><span>© {year} SERTI</span><span>{dict.ui.unique}</span></div></footer><FloatingWhatsApp settings={settings} dict={dict} /></>;
}
export async function PreviewBar({ dict }: { dict: Dictionary }) {
  return (await draftMode()).isEnabled ? <aside className="preview-bar">{dict.ui.preview} <Link href="/preview/exit" prefetch={false}>{dict.ui.exit} ↗</Link></aside> : null;
}
