import { locale } from 'next/root-params';
import { getDictionary } from '../../dictionaries';
import { emptySettings, getSettings } from '@/lib/api/server';
import { isLocale } from '@/lib/i18n';

export default async function UnavailableOrder() {
  const language = await locale();
  const dict = await getDictionary();
  const settings = isLocale(language) ? await getSettings(language).catch(() => emptySettings) : emptySettings;
  return <main id="main" className="commerce-page order-page">
    <header className="page-heading"><p className="eyebrow">SERTI · {dict.commerce.order}</p><h1>{dict.commerce.linkUnavailable}</h1></header>
    <div className="order-contact">
      {settings.whatsapp.general_url && <a className="text-link" href={settings.whatsapp.general_url} target="_blank" rel="noopener noreferrer">WhatsApp ↗</a>}
      {settings.support_email && <a className="text-link" href={`mailto:${settings.support_email}`}>{dict.commerce.contact} · {settings.support_email}</a>}
    </div>
  </main>;
}
